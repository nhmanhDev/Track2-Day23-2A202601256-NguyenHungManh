# Runbook 1 trang - Region chinh down

Runbook xu ly su co khan cap danh cho ky su on-call khi Region A gap su co va can failover sang Region B.

| # | Buoc | Lenh | Biet la xong khi | Ai lam |
|---|---|---|---|---|
| 1 | Xac nhan outage | `python chaos/kill_region.py status` | `a.ready=false` lien tiep >= 3 chu ky probe | On-call |
| 2 | Mo incident + bam gio RTO | `python dr/runbook.py --primary a --target b --backend fs` | ts ghi nhan vao `reports/runbook-run.jsonl` | On-call |
| 3 | Restore state o region phu | `python state/snapshot.py get --region b --backend fs` | Snapshot manifest duoc nap vao state/region-b/ | On-call |
| 4 | Scale pool warm->full | `python -c "import pathlib; pathlib.Path('state/region-b/pool_state').write_text('full')"` | /readyz cua Region B tra HTTP 200 (warmup xong) | On-call |
| 5 | DNS/LB cutover | `python -c "import pathlib; pathlib.Path('edge/active_region').write_text('b')"` | `curl localhost:8080/edge/state` tra active_region=b | On-call |
| 6 | Verify golden signals | `curl -s localhost:8080/v1/infer` (gui 10 req) | 100% request thanh cong, p95 < 100ms, error rate = 0% | On-call |
| 7 | Do RTO + postmortem | `python tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl` | rto_verdict: PASS va RTO <= 300s | Incident Commander |

---

## Quy trinh Rollback (Failback ve Region A)

### Dieu kien Rollback:
1. **Region A song lai va on dinh:** /readyz va /healthz cua Region A tra ve HTTP 200 lien tuc trong toi thieu 10 phut.
2. **Dong bo du lieu nguoc (Reverse Replication):** Du lieu vector moi duoc ghi nhan tren Region B trong suot thoi gian outage phai duoc backup va restore thanh cong ve Region A de tranh that thoat du lieu.
3. **GPU Warmup hoan tat tren Region A:** Model weights san sang tren VRAM, pool state chuyen ve full.

### Tham quyen quyet dinh:
- **Incident Commander (Chi huy su co)** phoi hop cung **Lead SRE** co tham quyen ra quyet dinh cutover luu luong nguoc lai ve Region A. Tuyet doi khong thiet lap auto-failback khong co circuit breaker de phong chong rui ro flap hai chieu.
