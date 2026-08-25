# RTO/RPO Evidence - Lab 23

Quy tac: moi con so o day tro ve mot dong log that (duong/dan.jsonl:so_dong).

## 1. Drill 1 - khong co DR (baseline)

| Chi so | Gia tri | Cach do | Evidence |
|---|---|---|---|
| t_outage | `2026-08-25T09:48:05` | chaos kill | `chaos/chaos-events.jsonl:1` |
| Request fail dau tien | `+0.5s` | dong ok:false dau tien sau t_outage | `reports/drill-1-nodr.jsonl:18` |
| Request thanh cong sau do | khong co | khong co dong ok:true nao sau t_outage | `reports/measure-drill-1.json` |
| RTO | `NO_RECOVERY` | tools/measure_rto.py | `reports/measure-drill-1.json` |

## 2. Drill 2 - co DR

| Moc | +giay tu t_outage | Cach do | Evidence |
|---|---|---|---|
| t_outage (moc 0) | 0 | action:kill | `chaos/chaos-events.jsonl:3` |
| User thay loi dau tien | `+0.1s` | dong ok:false dau | `reports/drill-2-withdr.jsonl:25` |
| Health check phat hien | `+15.1s` | to:UNHEALTHY, region:a | `reports/health-events.jsonl:2` |
| Snapshot restore xong | `+20.9s` | step:2_restore_snapshot | `reports/failover-events.jsonl:6` |
| Region phu ready | `+27.2s` | step:4_wait_ready | `reports/failover-events.jsonl:8` |
| DNS cutover | `+27.2s` | step:5_dns_cutover | `reports/failover-events.jsonl:9` |
| **RTO do duoc** | `28.4s` | dong ok:true dau sau loi | `reports/drill-2-withdr.jsonl:39` |

| Chi so | Do duoc | Muc tieu (slide 1) | Verdict |
|---|---|---|---|
| RTO - Inference API | `28.4s` | 300s (5 phut) | PASS |
| RPO - Vector DB | `8.01s` / `4` doc | 300s (5 phut) | PASS |

## 3. RTO cua toi gom nhung gi

| Thanh phan | Giay | No den tu dau | Giam duoc bang cach nao |
|---|---|---|---|
| Health-check detect floor | `15.0s` | interval_s * threshold (5s * 3) trong `reports/health-events.jsonl:2` | Giam interval xuong 2s hoac threshold xuong 2, nhung can can nhac rui ro flapping |
| Snapshot restore | `0.01s` | 2_restore -> 3_scale trong `reports/failover-events.jsonl:6` | Tang tan suat backup hoac chuyen sang streaming replication |
| GPU pool warm-up | `6.32s` | waited_s o 4_wait_ready trong `reports/failover-events.jsonl:8` | Pre-load model weights vao GPU VRAM, duy tri pool o trang thai warm cao |
| DNS/LB TTL cache | `1.2s` | t_recovered - t_cutover (28.4s - 27.2s) trong `reports/drill-2-withdr.jsonl:39` | Giam TTL cua DNS/Proxy (vi du xuong 1s) hoac dung Anycast LB |
