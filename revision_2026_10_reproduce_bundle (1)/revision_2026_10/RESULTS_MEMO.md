# Memo kết quả Giai đoạn 0–1: phân tích bổ sung theo "Hướng sửa bài"

Ngày: 2026-10-04 · Phạm vi: GVHD mục 1 (triple interaction) và mục 4 (FTA–depth), cùng 3 kiểm tra tùy chọn.
Chưa sửa câu chữ nào trong bài; `D:\uni\AIID\final_v2.md` hiện vẫn là bản sao của `final.md`.

## Tóm tắt nhanh

1. **Tái lập đạt.** Công cụ trên máy này cho lại đúng các con số của bài (sai lệch < 10⁻⁷), kể cả SE cluster hai chiều.
2. **Mục 4 (FTA–depth).**
   - FTA và depth lồng nhau, tương quan 0,73.
   - Sau khi khử fixed effects, VIF của hai biến tương tác chỉ khoảng 2,2: đa cộng tuyến ở mức vừa phải.
   - Tại depth trung vị, joint model cho lại gần đúng ước lượng FTA-only, nên hai đặc tả không mâu thuẫn nhau.
3. **Mục 1 (link size): kịch bản C theo quy tắc đã ghi trước.**
   - Tác động âm của GPR×Depth lên survival **không** tập trung ở link nhỏ.
   - Theo điểm phần trăm, nó gần 0 ở link < 10k USD và lớn nhất ở link ≥ 1 triệu USD.
   - So với tỷ lệ exit nền, link lớn luôn bị tác động mạnh nhất, dù dùng thiết kế nào.
   - Lập luận "selective pruning / fixed compliance cost" **không được dữ liệu ủng hộ**.
4. **Phát hiện hậu kiểm, quan trọng nhất:**
   - Các hiệp định có ≥ 30 provisions là 86% cặp nội khối EU (dưới 30 provisions thì 0%).
   - Bỏ cặp nội khối EU thì hiệu ứng survival chính (Bảng 4 cột 5) mất: −0,0052 (p = 0,007) → −0,0012 (p = 0,38).
   - Ngược lại, hiệu ứng dương của depth lên **giá trị** thương mại theo GPR cặp nước (Bảng 7) còn mạnh hơn khi bỏ EU.
5. **Figure 3 cần sửa.** Với hiệp phương sai thật, khoảng tin cậy chỉ loại trừ 0 từ **32 provisions** trở lên, không phải ≈19.
6. **Hai kiểm tra tùy chọn còn lại:**
   - COVID không phải nguồn tạo ra kết quả: bỏ 2020 hoặc 2020–2021, hệ số còn mạnh hơn.
   - Tính theo giá trị, số link mất đi chỉ tương ứng khoảng 0,1 điểm phần trăm giá trị thương mại.

---

## Giai đoạn 0 — Chuẩn bị

- Thư mục làm việc: `AIID_DTA_GPR/revision_2026_10/` (gồm `scripts/`, `tables/`, `figures/`, `logs/`). Không có file cũ nào bị sửa.
- `README.md` ghi đặc tả và quy tắc phân loại A/B/C **trước khi** chạy mô hình.
- Mọi phân tích ngoài kế hoạch đều được ghi rõ là *hậu kiểm (post-hoc)*.

## 1.1 Cổng tái lập — ĐẠT

| Đối tượng tái lập | Hệ số | SE | N |
|---|---|---|---|
| Bảng 4 cột (4), (5) — survival | sai lệch ≤ 2,3 × 10⁻¹² | ≤ 1,1 × 10⁻⁷ | 8.045.131 = 8.045.131 |
| Leave-one-year-out, bỏ 2020 | khớp tới 8 chữ số | khớp | 7.483.836 = 7.483.836 |
| Bảng 7 Panel B — survival theo GPR cặp nước | khớp | khớp | 1.878.443 = 1.878.443 |
| Bảng 7 Panel A — PPML (pyfixest) | sai lệch ≤ 2 × 10⁻¹³ | ≤ 7 × 10⁻⁸ | 2.520.781 = 2.520.781 |

PPML trên toàn mẫu (16,75 triệu dòng, Bảng 3) không chạy lại được vì thiếu RAM; mọi con số Bảng 3 giữ nguyên.

## 1.2 FTA và DTAdepth (GVHD mục 4) — kiểm tra nội bộ

| Chỉ tiêu | Survival | Trade value | Re-entry | Cặp-năm |
|---|---|---|---|---|
| Tương quan FTA–depth | 0,743 | 0,733 | 0,731 | 0,734 |
| Tương quan GPR×FTA với GPR×Depth | 0,837 | 0,816 | 0,811 | 0,798 |
| — sau khi khử fixed effects | 0,742 | 0,734 | 0,745 | – |
| VIF của hai biến tương tác (sau khi khử FE) | 2,2 | 2,2 | 2,3 | – |
| VIF của FTA, depth (biến mức) | 3,9 | 3,6 | 4,0 | – |
| % quan sát FTA có depth = 0 | 0,19% | 0,27% | 0,35% | 0,31% |
| Depth trung vị trong nhóm FTA (provisions) | 14 | 12 | 11 | 11 |

- **Lồng nhau.** Depth > 0 chỉ khi FTA = 1. Hệ số FTA trong joint model là phản ứng tại depth = 0, ở mép dữ liệu.
- **Đa cộng tuyến vừa phải.** VIF ≈ 2,2 nghĩa là SE của hai biến tương tác bị phóng đại khoảng 1,5 lần khi ước
  lượng chung. Con số này khớp với chênh lệch SE thực tế giữa cột (2) và cột (3) của Bảng 3 (0,0047 → 0,0078).
- **Có biến thiên độc lập.**
  - Trong 12.720 cặp, 1.967 cặp ký hiệp định mới trong giai đoạn 2007–2023, và 853 cặp thay đổi depth khi hiệp
    định vẫn còn hiệu lực.
  - Depth chủ yếu khác nhau giữa các cặp (SD 9,2 provisions), rất ít thay đổi theo thời gian trong cùng một cặp
    (SD 1,1).
- **Joint model không mâu thuẫn với mô hình riêng lẻ.** Tại depth trung vị:
  - survival: −0,45 pp (p = 0,225) so với FTA-only −0,47 pp (p = 0,223);
  - trade value: −0,0264 so với FTA-only −0,0241 (chỉ có point estimate).
  - Việc hệ số depth đổi dấu ở Bảng 3 (−0,0053 → +0,0099) là vì ở cột (2) depth còn đại diện cho cả việc có
    hiệp định.
- **Một đặc điểm phân phối quan trọng.** Depth có hai đỉnh: khoảng 3–18 provisions (hiệp định thông thường) và
  34–35 provisions (gần như toàn bộ là EU). Xem dải phân phối dưới Figure 3 mới.

Đề xuất câu cho bài (mục 3.4 hoặc 4.1):

> Agreement depth is defined only for pairs with an agreement in force, so the two moderators are nested:
> depth is positive only when FTA equals one, and fewer than 0.4 percent of agreement observations carry no
> enforceable provision. They correlate at 0.73, and the two interactions at 0.73–0.76 after the fixed
> effects are partialled out, which inflates their variances by a factor of about 2.2 in the joint
> specification. The FTA coefficient there describes an agreement with no enforceable provision, at the edge
> of the data, and the depth coefficient the gradient among agreement pairs; at the median depth of agreement
> links the joint estimates reproduce the FTA-only estimates (−0.0264 against −0.0241 for trade values; −0.45
> against −0.47 percentage points for survival).

## 1.3 Link-size heterogeneity (GVHD mục 1)

### Kết quả theo kế hoạch đã ghi trước

**Bốn nhóm size (mô hình gộp S3, cluster hai chiều).** Hệ số GPR×Depth, tính bằng điểm phần trăm survival cho mỗi
SD của GPR và mỗi 10 provisions:

| Giá trị link năm t−1 | % số link | Tỷ lệ exit | GPR×Depth (pp) | p | So với tỷ lệ exit nền | p |
|---|---|---|---|---|---|---|
| < 10k USD | 29,5% | 31,3% | **+0,11** | 0,59 | −0,4% | 0,59 |
| 10k–100k | 21,9% | 12,7% | −0,17 | 0,21 | +1,3% | 0,21 |
| 100k–1M | 22,3% | 4,3% | −0,39 | 0,010 | +9,0% | 0,010 |
| ≥ 1M | 26,3% | 1,1% | **−0,50** | 0,0007 | **+44,5%** | 0,0007 |

Các kiểm định:
- Chênh lệch giữa nhóm nhỏ nhất và lớn nhất: +0,62 pp (p = 0,039). Hiệu ứng ở link nhỏ *kém âm hơn* hẳn.
- Kiểm định bốn hệ số bằng nhau: p = 0,084.
- Kiểm định bốn hiệu ứng tương đối bằng nhau: p = 0,0015.

**Biến size liên tục:**
- Đúng như GVHD đề xuất, với LaggedTrade = ln(1 + triệu USD): hệ số triple interaction = −0,016 (p = 0,76). Không
  có khác biệt hệ thống, vì thang đo này gần như bằng 0 với mọi link dưới 100k USD.
- Với size đo bằng ln(USD): hệ số = −0,044 pp mỗi đơn vị log (p = 0,14 cluster hai chiều; p < 0,001 cluster cặp).
  Hiệu ứng ngụ ý: −0,01 pp ở 1k USD, −0,21 pp ở 100k, −0,31 pp ở 1M, −0,41 pp ở 10M.
- Thay GPR×size bằng size×year (S1b, S3b): kết quả gần như không đổi.

**Phân loại: kịch bản C** theo cả ba cách (S3 cluster hai chiều, S3 cluster cặp, S3b).

### Chẩn đoán hậu kiểm: vì sao Panel B của bài cho hình ảnh khác?

Panel B (Bảng 5) ước lượng lại toàn bộ mô hình trên mẫu link ≥ 100k / ≥ 1M, nghĩa là mọi fixed effect được ước lượng
lại trong từng mẫu con. Tôi thử các thiết kế dưới đây:

| Thiết kế | < 10k | 10k–100k | 100k–1M | ≥ 1M | Kịch bản |
|---|---|---|---|---|---|
| (a) Mô hình riêng cho từng nhóm (giống Panel B) | −0,32 (p 0,22) | −0,03 | −0,03 | −0,14 (p 0,019) | – |
| (b) Mô hình gộp, FE theo năm riêng từng nhóm | −0,33 (p 0,19) | −0,11 | −0,13 | −0,18 (p 0,001) | C |
| (c) S3, bỏ năm 2022 | −0,10 | −0,18 | −0,36 | −0,51 (p 0,071) | C |
| (d) S3, bỏ nội khối EU | +0,35 (p 0,03) | +0,03 | −0,09 | −0,11 (p 0,22) | C |

- Khi FE được ước lượng riêng theo nhóm, độ dốc theo size **phẳng lại**. Điểm ước lượng ở link nhỏ nhất là lớn nhất,
  nhưng không có ý nghĩa thống kê, và chênh lệch giữa các nhóm cũng không có ý nghĩa (p = 0,55).
- **So với rủi ro exit nền, thiết kế nào cũng cho link lớn bị tác động mạnh nhất** (+16% đến +45% ở nhóm ≥ 1M,
  so với khoảng +1% ở nhóm < 10k).
- Câu hiện tại của bài, "restricting to links above USD 100,000 reduces it by roughly three-quarters… small flows,
  which are pruned first", dựa trên việc so hệ số giữa các mẫu con. Cách so này không phải là một kiểm định về khác
  biệt theo size, và nó cho kết luận ngược lại khi tính theo tỷ lệ.

**Kết luận cho mục 1:** không có bằng chứng tác động âm tập trung ở link nhỏ. Theo GVHD mục 2, bài không nên dùng
"selective pruning" hay "fixed compliance costs" làm cách giải thích kết quả survival.

### Phát hiện hậu kiểm: kết quả survival đến từ các cặp nội khối EU

| Mô hình | GPR×Depth | p | GPR×FTA | p | N |
|---|---|---|---|---|---|
| Bảng 4 cột 5 (gốc) | −0,0052 | 0,007 | +0,0028 | 0,086 | 8.045.131 |
| Bỏ cặp nội khối EU | −0,0012 | 0,38 | −0,0008 | 0,65 | 7.255.127 |
| Toàn mẫu + GPR×EU | −0,0014 | 0,30 | −0,0009 | 0,62 | 8.045.131 |
| ↳ hệ số GPR×EU | **−0,0135** | < 0,001 | | | |

- **Nguyên nhân về mặt dữ liệu:** trong 14.290 cặp-năm có từ 30 provisions trở lên, 86% là cặp nội khối EU; dưới
  30 provisions thì 0%. Ở đầu trên của thang đo, "depth" gần như chính là "thuộc thị trường chung EU".
- **Không phải do mất power:** SE khi bỏ EU (0,0013) còn nhỏ hơn SE gốc (0,0017), và khoảng tin cậy mới không chứa
  −0,0052.
- **Bảng 7 (44 nền kinh tế, GPR theo từng nước):**

| Biên | Thước đo GPR | Đầy đủ | Bỏ nội khối EU |
|---|---|---|---|
| Survival (LPM) | Toàn cầu, mẫu hẹp | −0,0038 (p 0,001) | −0,0012 (p 0,14) |
| Survival (LPM) | GPR trung bình theo cặp nước | −0,0017 (p < 0,001) | −0,0004 (p 0,50) |
| Trade value (PPML) | Toàn cầu, mẫu hẹp | +0,0160 (p 0,14) | +0,0122 (p 0,34) |
| Trade value (PPML) | GPR trung bình theo cặp nước | +0,0280 (p 0,018) | **+0,0413 (p 0,003)** |

Hai biên vì vậy đến từ hai nhóm cặp nước khác nhau:
- Tác động âm lên survival chỉ có ở nội khối EU.
- Tác động dương lên giá trị (theo GPR cặp nước) không phụ thuộc EU, thậm chí mạnh hơn khi bỏ EU.

"Two-margin divergence" vẫn đúng về mặt mô tả trên toàn mẫu. Nhưng không thể diễn giải nó là *một* cơ chế của depth
(depth giữ giá trị nhưng làm mỏng mạng lưới).

**Giới hạn của phát hiện này:**
- GPR toàn cầu chỉ có một chuỗi thời gian. Vì vậy GPR×EU không tách được tác động địa chính trị với các cú sốc riêng
  của EU trùng thời điểm, như khủng hoảng năng lượng 2022 hay thay đổi thống kê nội khối.
- Bỏ 2020–2021 thì kết quả gốc còn mạnh hơn; bỏ 2022 thì vẫn là −0,0068 (p = 0,066). Như vậy không một năm nào tự
  tạo ra kết quả.
- Cách đọc hợp lý nhất: các đỉnh GPR giai đoạn 2007–2023 (Crimea 2014, Ukraine 2022) đều là xung đột ở châu Âu,
  và link nội khối EU nằm gần các cú sốc đó nhất. Tuy vậy đây chỉ là giả thuyết, chưa được kiểm định.

## 1.4 Ba kiểm tra tùy chọn

**Figure 3 với hiệp phương sai thật** (`figures/fig3_marginal_effect_true_cov.png`):
- Hiệp phương sai giữa GPR×FTA và GPR×Depth là dương (tương quan +0,67, cluster hai chiều), nên dải tin cậy rộng
  hơn hình cũ.
- Hiệu ứng tổng bằng 0 tại 5,4 provisions (không đổi).
- Khoảng tin cậy 95% loại trừ 0 **từ 32 provisions** trở lên (p < 0,10 từ 21 provisions).
- Hình cũ ghi ≈19 vì vừa giả định hiệp phương sai bằng 0, vừa dùng giá trị tới hạn 1,96 thay cho t(15).
- Hệ quả: chỉ các hiệp định sâu nhất, gần như toàn bộ là EU, có hiệu ứng tổng âm có ý nghĩa thống kê.
- Hình mới có thêm dải phân phối depth, cho thấy rõ hai đỉnh.

**COVID:**

| Mẫu | GPR×Depth | p (hai chiều) |
|---|---|---|
| Đầy đủ | −0,0052 | 0,007 |
| Bỏ 2020 (năm có tỷ lệ exit cao nhất, 16,2%) | −0,0054 | 0,020 |
| Bỏ 2020–2021 | −0,0075 | < 0,001 |

Có thể viết: "excluding the pandemic years strengthens rather than weakens the estimate."

**Survival có trọng số theo giá trị:**
- GPR×Depth = −0,0010 (p = 0,086). Tỷ lệ exit tính theo giá trị chỉ là 0,25%, so với 13,3% khi tính theo số link.
- Ý nghĩa: các link bị mất do GPR×Depth tương ứng khoảng 0,1 điểm phần trăm giá trị thương mại (mỗi SD × 10
  provisions). Nhỏ về tuyệt đối, nhưng lớn so với nền 0,25%.
- Điều này giải thích vì sao biên giá trị gần như không ghi nhận các lần mất link.

## Hệ quả cho Giai đoạn 2 (sửa bài)

Những câu chắc chắn phải bỏ hoặc sửa:

| Vị trí | Câu hiện tại | Vì sao |
|---|---|---|
| Abstract | "concentrated among smaller links: … fixed-cost mechanism" | Mục 1: kịch bản C |
| §4.4.1 sau Fig. 3; §4.4.2 Panel B | "pruned first", "core relationships persist", "quasi-fixed overheads bear disproportionately on small flows" | Kịch bản C; Panel B không phải kiểm định |
| §4.4.1 | "interval excludes zero only beyond roughly 19 provisions" | Đúng là từ 32 provisions |
| §4.4.1 | "Below this threshold the preferential tariff advantage dominates…" | Diễn giải cơ chế không có kiểm định |
| §4.6, §5.1, Intro | "Depth protects relationship value while pruning relationship count"; "the small and young ones" | Hai biên đến từ hai nhóm cặp khác nhau; "young" chưa từng kiểm định |
| §5.1 | "protective one under pair-specific risk" | Mâu thuẫn với chính phần sửa DA-1 ở §4.6 |

Những phần mới đề xuất đưa vào bài:
- 4.2: bảng hoặc hình link-size (S3 + mô hình riêng từng nhóm) và đoạn ngắn "no concentration among small links".
- 4.4: kiểm tra EU, COVID, Figure 3 mới.
- 3.4: đoạn về quan hệ FTA–depth (câu đã soạn sẵn ở trên).
- 5.2: viết lại hoàn toàn. Không viết về "selective adjustment" nữa, mà về chuyện tác động lên survival tập trung ở
  nội khối EU và ở link lớn, kèm các cách giải thích thay thế.

## Cần bạn quyết định trước Giai đoạn 2

1. **Cách đưa phát hiện EU vào bài:**
   - (a) chỉ là một robustness check ở 4.4, kèm một đoạn ở Discussion;
   - (b) đưa thành một kết quả chính trong 4.2 ("where the survival effect comes from").

   Tôi đề xuất (b): đây là thông tin quan trọng nhất để diễn giải depth, và giấu nó ở robustness sẽ rủi ro nếu
   reviewer tự phát hiện. Nên hỏi ý GVHD vì nó thay đổi câu chuyện chính của bài.
2. **Có chạy thêm không?** (đều tùy chọn)
   - PPML toàn mẫu bỏ EU (Bảng 3): cần giải phóng RAM, khoảng 15 triệu dòng;
   - leave-one-year-out cho hệ số GPR×EU, để xem nó đến từ 2014–15 hay 2022;
   - kiểm định chính thức EU và ngoài EU cho biên giá trị.
3. **Hình link-size trong bài:** dùng hình hai bảng hiện tại (gộp + riêng từng nhóm) hay chỉ một thiết kế?

## File đã tạo

- `scripts/`: `r17_common.py` (hàm dùng chung), `17a`–`17f` (mỗi bước một script, chạy độc lập).
- `tables/`: `17a_*`–`17f_*.csv` (toàn bộ hệ số, cả hai cách cluster).
- `figures/`: `fig3_marginal_effect_true_cov.png/.pdf`, `fig_size_groups.png/.pdf`.
- `logs/`: log từng bước, trạng thái cổng tái lập `17a_gate_status.txt`, phân loại kịch bản `17c_scenario.txt`.
- `cache/`: mảng trung gian (11 GB trên ổ D, xóa được bất cứ lúc nào; chạy lại script sẽ tự tạo lại).
