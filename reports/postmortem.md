# Postmortem - DR Drill Lab 23

Theo dung template "Sau Failover: Blameless Postmortem". Blameless: tap trung vao viec hoan thien quy trinh va he thong, khong quy trach nhiem ca nhan.

## 1. Timeline (moi dong co evidence path:line)

| ISO time | Su kien | Evidence |
|---|---|---|
| `2026-08-25T09:55:34` | Outage bat dau (Region A bi netblock) | `chaos/chaos-events.jsonl:3` |
| `2026-08-25T09:55:35` | User dau tien bi anh huong (ConnectTimeout 503) | `reports/drill-2-withdr.jsonl:25` |
| `2026-08-25T09:55:50` | Health check phat hien va chuyen UNHEALTHY (sau 3 lan fail) | `reports/health-events.jsonl:2` |
| `2026-08-25T09:55:55` | Operator confirm cutover va khoi chay runbook failover | `reports/runbook-run.jsonl:2` |
| `2026-08-25T09:56:03` | Resolved (request dau tien OK tu region phu Region B) | `reports/drill-2-withdr.jsonl:39` |

## 2. RTO/RPO do duoc vs muc tieu - gap o buoc nao?

- RTO muc tieu: 300s - do duoc: `28.4s` - gap: vuot muc tieu `271.6s` (dat chuan SLA).
- RPO muc tieu: 300s - do duoc: `8.01s` (`4` doc bi mat) - gap: vuot muc tieu `291.99s`.
- **Buoc ton nhieu giay nhat:** `Health-check detect floor (15.0s)` - chiem 52.8% tong thoi gian RTO vi can cho 3 chu ky tham do lien tiep (5s/lan) de dam bao khong bi false positive / flapping.

## 3. Root cause (5 whys)

Neu day la mot outage thuc te trong moi truong san xuat:
1. *Tai sao user gap loi 503?* Vi Region A gap su co phan manh mang (network partition / dropped packets) khien moi request gui toi bi timeout.
2. *Tai sao he thong khong phuc hoi ngay lap tuc?* Vi can thoi gian de Health Checker xac nhan su co du 3 chu ky lien tiep nham tranh kich hoat failover sai.
3. *Tai sao Region B khong the nhan request ngay khi Region A down?* Vi Region B o trang thai Standby (warm), vector DB chua nap du lieu va GPU pool chua duoc scale full.
4. *Tai sao can nap snapshot va scale pool?* Vi kien truc toi uu chi phi (Active-Warm Standby) chi luu tru ban sao du phong va giu tai nguyen toi thieu cho den khi kich hoat su co.
5. *Tai sao runbook can xac nhan ban tu dong?* De nguoi van hanh (On-call) kiem soat quyet dinh chuyen huong luu luong, tranh tinh trang hai vung flap qua lai gay gian doan kep.

## 4. Action items (co owner + deadline)

| # | Action item | Owner | Deadline | Giam RTO/RPO bao nhieu giay |
|---|---|---|---|---|
| 1 | Nang cap co che Health Check sang adaptive interval (2s khi nghi ngo loi) | SRE Team | 2026-09-05 | Giam ~9s RTO |
| 2 | Chuyen doi tu snapshot batch (30s) sang Change Data Capture (CDC) streaming replication | Data Infra Team | 2026-09-12 | Giam RPO xuong < 1s |

## 5. Ba cau hoi bat buoc tra loi

1. **`interval * threshold` cua ban la bao nhieu giay? No chiem bao nhieu % RTO?**
   - `interval = 5.0s`, `threshold = 3` -> Detection floor la `15.0s`.
   - No chiem `15.0 / 28.4 = 52.8%` tong RTO.

2. **Neu ha interval xuong 1s, RTO giam may giay - va ban tra gia gi (flapping)?**
   - Neu ha interval xuong 1s (voi threshold=3), detection floor giam tu 15s xuong 3s -> RTO giam khoang 12 giay.
   - **Cai gia phai tra:** Nguy co cao bi hien tuong **Flapping** (chuyen doi vung lien tuc khi co bien dong mang tam thoi / transient network jitter), gay ngat quang ket noi cua nguoi dung, phan manh du lieu 2 vung (split-brain) va tang dot bien tai len ca 2 he thong.

3. **Neu outage keo dai 6 gio va region chinh mat du lieu vinh vien, `docs_lost` cua ban co nghia gi voi khach hang?**
   - `docs_lost = 4` nghia la co 4 tai lieu/giao dich cua khach hang duoc tao trong khoang thoi gian giua lan snapshot gan nhat va thoi diem sap nguon bi mat tren Region B.
   - Doi voi khach hang, dieu nay tuong ung voi viec 4 giao dich/yeu cau do chua duoc dong bo va can duoc khoi phuc tu hang doi thong diep (Kafka/Event Store) hoac thong bao cho khach hang gui lai yeu cau.
