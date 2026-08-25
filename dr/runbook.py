"""BƯỚC 3c — SINH VIÊN VIẾT. Tự động hoá runbook §4 "Runbook: Region Chính Down".

7 bước trên slide, mỗi bước 1 dòng log có ts. Log này CHÍNH LÀ timeline của postmortem.
  1 xac_nhan_outage          — probe cả 2 region, đừng tin 1 lần fail (dùng nhiều lần
                              hoặc gọi health_checker.probe nếu đã viết xong 3a)
  2 thong_bao_incident       — ts của dòng này là mốc "operator biết tin", LUÔN LUÔN
                              SAU t_outage trong chaos-events (không thể trùng — operator
                              không thể biết ngay giây outage xảy ra). Ghi cả 2 ts vào
                              log để postmortem tính được "độ trễ thông báo".
  3 scale_gpu_pool           — gọi HÀM `failover.failover(...)` MỘT LẦN DUY NHẤT. Hàm
                              đó tự làm đủ 5 bước con (verify/restore/scale/wait/cutover)
                              và tự ghi log riêng vào reports/failover-events.jsonl.
  4 verify_state_replica     — KHÔNG gọi lại failover — chỉ ĐỌC kết quả (vector count +
                              weights ở region phụ) từ dict mà bước 3 trả về, để log vào
                              runbook-run.jsonl cho postmortem đọc 1 chỗ duy nhất.
  5 dns_cutover              — cũng chỉ đọc lại: kết quả cutover có ok hay không.
  6 verify_golden_signals    — 10 request thật vào region phụ: p95 latency + error rate
  7 post_incident            — elapsed_s + lệnh đo RTO

BÁN TỰ ĐỘNG, KHÔNG FULL-AUTO (§4: "failover đầu tiên nên là bán tự động — alert +
1-click confirm — tránh flapping gây failover 2 chiều liên tục"). Mặc định phải hỏi
người vận hành confirm; --auto chỉ dùng trong CI/khi chấm điểm.

Chạy:  python dr/runbook.py --primary a --target b --backend fs
"""
import argparse
import json
import pathlib
import sys
import time

import httpx

sys.path.insert(0, ".")
from dr import failover as fo  # noqa: E402

LOG = pathlib.Path("reports/runbook-run.jsonl")
URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}


from dr.health_checker import probe  # noqa: E402


def step(n: int, name: str, **kw) -> dict:
    """Ghi 1 dòng {ts, iso, step, name, ...} vào LOG."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "step": n,
        "name": name,
        **kw,
    }
    with LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print("RUNBOOK", json.dumps(rec))
    return rec


def confirm(auto: bool, msg: str) -> bool:
    """auto=True -> True; ngược lại hỏi y/N. Đừng bỏ hàm này đi."""
    if auto:
        return True
    try:
        ans = input(f"{msg} [y/N]: ")
        return ans.strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def run(primary: str, target: str, backend: str, auto: bool) -> dict:
    """7 bước runbook theo kịch bản chuẩn."""
    t_start = time.time()

    # Bước 1: 1 xac_nhan_outage
    p_ready, p_reason = probe(primary, timeout=1.5)
    t_ready, t_reason = probe(target, timeout=1.5)
    step(1, "xac_nhan_outage",
         primary=primary, primary_ready=p_ready, primary_reason=p_reason,
         target=target, target_ready=t_ready, target_reason=t_reason)

    # Bước 2: 2 thong_bao_incident
    confirmed = confirm(auto, f"Xac nhan khoi dong quy trinh failover tu {primary} sang {target}?")
    if not confirmed:
        step(2, "thong_bao_incident", confirmed=False, status="aborted_by_operator")
        return {"ok": False, "error": "aborted_by_operator"}
    step(2, "thong_bao_incident", confirmed=True, primary=primary, target=target,
         msg=f"Operator khoi dong failover tu region-{primary} sang region-{target}")

    # Bước 3: 3 scale_gpu_pool (gọi hàm failover đúng 1 lần)
    fo_res = fo.failover(target=target, backend=backend)
    step(3, "scale_gpu_pool", target=target, failover_ok=fo_res.get("ok"), detail=fo_res)
    if not fo_res.get("ok"):
        return {"ok": False, "error": "failover_failed", "detail": fo_res}

    # Bước 4: 4 verify_state_replica
    step(4, "verify_state_replica",
         target=target,
         rpo_seconds=fo_res.get("rpo_seconds"),
         docs_lost=fo_res.get("docs_lost"),
         embed_model_version=fo_res.get("embed_model_version"))

    # Bước 5: 5 dns_cutover
    step(5, "dns_cutover", active_region=target, ok=fo_res.get("ok"))

    # Bước 6: 6 verify_golden_signals (gửi 10 request đo p95 & error rate)
    latencies = []
    errors = 0
    with httpx.Client(timeout=3.0) as c:
        for i in range(10):
            t0 = time.time()
            try:
                r = c.get("http://127.0.0.1:8080/v1/infer", params={"q": f"golden-check-{i}"})
                if r.status_code == 200:
                    latencies.append((time.time() - t0) * 1000)
                else:
                    errors += 1
            except Exception:
                errors += 1

    p95 = round(sorted(latencies)[int(len(latencies) * 0.95)], 1) if latencies else None
    err_rate = round(errors / 10.0, 2)
    step(6, "verify_golden_signals", req_count=10, error_rate=err_rate, p95_latency_ms=p95)

    # Bước 7: 7 post_incident
    elapsed = round(time.time() - t_start, 2)
    step(7, "post_incident", elapsed_s=elapsed,
         measure_cmd="python tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl")

    return {
        "ok": True,
        "primary": primary,
        "target": target,
        "elapsed_s": elapsed,
        "rpo_seconds": fo_res.get("rpo_seconds"),
        "docs_lost": fo_res.get("docs_lost"),
        "p95_latency_ms": p95,
        "error_rate": err_rate,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--primary", default="a")
    p.add_argument("--target", default="b")
    p.add_argument("--backend", default="fs", choices=["fs", "minio"])
    p.add_argument("--auto", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.primary, a.target, a.backend, a.auto), indent=2))
