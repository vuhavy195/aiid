# Danh sách lỗi & mâu thuẫn cần sửa — BẢN 2 (đã kiểm chứng bằng dữ liệu gốc)

**File được audit:** `results.md` (176.018 bytes) + toàn bộ `AIID_DTA_GPR/python`, `AIID_DTA_GPR/r`, `AIID_DTA_GPR/data`, `AIID_DTA_GPR/outputs`
**Phạm vi:** Mục 4 Results and Discussion (dòng 29–304) + toàn bộ bảng/hình + tầng code sinh ra chúng
**Không audit:** Mục 1, 2, 3, 5, ABSTRACT, REFERENCES — hiện trống hoàn toàn

---

## ⚠️ ĐỌC TRƯỚC — BẢN 1 CÓ 4 LỖI SAI

Bản 1 của tài liệu này được viết **chỉ bằng cách đọc `results.md`**, không chạy lại dữ liệu. Bản 2 này được viết sau khi đã chạy lại toàn bộ pipeline audit trên panel parquet thật và đối chiếu từng ô với CSV gốc.

**Bốn mục sau của bản 1 là SAI. Không được làm theo:**

| Mục | Bản 1 nói | Thực tế |
|---|---|---|
| **B1** (bản 1 xếp ưu tiên cao nhất) | `p = 0.007` sai, phải sửa SE thành `0.0019` | `p = 0.007` **đúng tuyệt đối**. Sửa theo bản 1 sẽ đưa lỗi vào bảng đang đúng. |
| **B4** | 5 bundle chỉ chứa 12 điều khoản; competition policy không thuộc bundle nào; nên thêm bundle thứ 6 | Code có **16** điều khoản, **cả 16 đều thuộc bundle**. Thêm bundle thứ 6 sẽ khiến Methods không khớp code. |
| **B7** (bản 1 ghi "Ưu tiên: Cao, có thể khiến toàn bộ Table A4 bị loại") | Thang depth tối đa 14 → hàng 20/30 của A4 là ngoại suy | Thang depth chạy tới **38**. Không có ngoại suy. |
| **E3** | Ngưỡng "12 điều khoản" đã kiểm chứng đúng | **Không kiểm chứng được** — hình sinh ra nó không có code, không có dữ liệu. |

Các mục còn lại của bản 1 đã được kiểm lại và **giữ nguyên hiệu lực**.

---

## MỤC LỤC

- [Kết quả kiểm chứng lại toàn bộ số liệu](#kết-quả-kiểm-chứng-lại-toàn-bộ-số-liệu)
- [Nhóm A — Lỗi hình thức (10 lỗi)](#nhóm-a--lỗi-hình-thức)
- [Nhóm B — Mâu thuẫn số liệu (5 lỗi, đã loại 2 lỗi ma)](#nhóm-b--mâu-thuẫn-số-liệu)
- [Nhóm C — Overclaim (7 lỗi)](#nhóm-c--overclaim-diễn-giải-vượt-quá-bằng-chứng)
- [Nhóm D — Thiếu sót nội dung](#nhóm-d--thiếu-sót-nội-dung)
- [**Nhóm G — Lỗi tầng code (MỚI, 4 lỗi)**](#nhóm-g--lỗi-tầng-code)
- [Nhóm E — Đã kiểm chứng ĐÚNG](#nhóm-e--đã-kiểm-chứng-đúng)
- [Nhóm F — Cơ hội đang bỏ phí](#nhóm-f--cơ-hội-đang-bỏ-phí)
- [Thứ tự sửa đề xuất](#thứ-tự-sửa-đề-xuất)
- [Phụ lục — Abstract đã xoá](#phụ-lục--abstract-đã-xoá-lưu-để-tham-chiếu)

---

## KẾT QUẢ KIỂM CHỨNG LẠI TOÀN BỘ SỐ LIỆU

### Đã chạy lại được gì

R **không được cài** trên máy → không re-fit được PPML/LPM. Nhưng toàn bộ panel parquet (9 GB) và CSV hệ số còn nguyên, nên đã chạy lại được bằng Python + DuckDB:

- toàn bộ audit pipeline trên dữ liệu thật (row count, group count, phân phối biến)
- mọi con số dẫn xuất từ hệ số (p-value, %effect, CI, BH-FDR, net effect)
- diff từng ô `results.md` ↔ CSV gốc trong `outputs/`

### Kết quả

**`results.md` là bản chép trung thực từ output mô hình.**

| Hạng mục | Khớp | Lệch |
|---|---|---|
| Ô bảng (T3, T5, T6, A2, A3) | **162** | 3 (làm tròn chữ số cuối) |
| p-value & hiệu ứng trong thân bài (L67, L68, L215, L217, L259, L260) | **22** | 0 |
| Claim jackknife (L181–183) | **6/6** | 0 |
| Row count mọi panel vs hằng số `EXPECTED_*` trong script | **5/5** | 0 |

Panel audits chạy lại khớp chính xác:

```
PPML compact : 16.752.461 dòng | 985.562 nhóm pair–HS2 | 12.454 cluster | 17 năm | 88 chương | 47,52% zero
Survival     :  8.219.579 dòng | 16 năm | tỷ lệ sống sót nền 84,94% | tỷ lệ đứt gãy 15,06%
Recovery     :  1.237.520 sự kiện đứt gãy | tái gia nhập 1 năm 34,1% | 2 năm 49,7%
Country-GPR  :  2.520.781 dòng | 946 cặp không thứ tự
```

Claim jackknife ở L181–183 đúng đến từng chi tiết, kể cả con số rất cụ thể "15 of 16":

```
16/16 vòng | tất cả âm nghiêm ngặt | khoảng [-0,6801 ; -0,4019] pp   (bài ghi [-0,68 ; -0,40])
pair-cluster p<0.01 : 16/16      two-way p<0.10 : 16/16      two-way p<0.05 : 15/16
```

Table A4 nhất quán nội bộ hoàn hảo: bước giảm mỗi 10 điều khoản = **−0,3543 pp**, đúng bằng hệ số Table 7 (`−0,003543 × 100`).

### Lỗi số liệu duy nhất tìm thấy trong toàn bộ `results.md`

**Dòng 148** ghi `p < 0.001` trong khi Table 6 và CSV gốc đều là `p = 0.007`. Bảng đúng, thân bài sai. Xem [B1](#b1-thân-bài-l148-mâu-thuẫn-với-table-6).

---

## NHÓM A — LỖI HÌNH THỨC

Sửa nhanh, không cần quyết định nội dung.

### A1. Tiêu đề bài là của bài khác

- **Dòng:** 1
- **Hiện trạng:** `**CARBON PRICING, EMISSIONS ABATEMENT, AND ECONOMIC GROWTH IN THE GLOBAL GREEN TRANSITION**`
- **Sửa:** Thay bằng tiêu đề thật. Gợi ý: *"Can Deep Trade Agreements Absorb Geopolitical Shocks? Global Evidence from Intermediate-Goods Supply Chains"*.

### A2. Hai mục cùng mang số 3.3.1

- **Dòng:** 23 và 25 → đổi L25 thành `3.3.2`. (`3.3.3` ở L27 đã đúng.)

### A3. Table 5 lặp hàng tiêu đề ở cuối bảng

- **Dòng:** 162 → xoá.

### A4. Không có Table 1 và Table 2

- **Vấn đề:** Bài bắt đầu từ Table 3. Reviewer không biết phân phối của `DTA Depth` nên không đánh giá được độ lớn hiệu ứng.
- **Đã có sẵn số liệu** (từ kiểm chứng lại panel):

  | Thống kê | Giá trị |
  |---|---|
  | DTA depth — min / median / max | 0 / 0 / **38** điều khoản |
  | DTA depth — median trong nhóm có FTA | **12** điều khoản |
  | Tỷ lệ dòng có FTA đang hiệu lực | 35,8% |
  | Tỷ lệ dòng zero trade (PPML) | 47,52% |
  | Tỷ lệ sống sót nền (survival panel) | 84,94% |
  | Tỷ lệ đứt gãy nền | 15,06% |
  | Tái gia nhập 1 năm / 2 năm | 34,1% / 49,7% |

- **Sửa:** Table 1 = nguồn dữ liệu & định nghĩa biến; Table 2 = thống kê mô tả dùng chính các con số trên.

### A5. Appendix Table A1 được dẫn chiếu nhưng không có trong bài

- **Dòng:** 67 — *"Appendix Table A1 reports the complete ten-sector results."*
- **Tin tốt:** File **đã tồn tại**: `outputs/paper_outputs/appendix_tables/appendix_table_a1_full_sector_results.csv`, đủ 10 ngành với cột `Sector | GPR x FTA | BH-FDR p: FTA | GPR x DTA depth | BH-FDR p: Depth | Observations`.
- **Sửa:** Chỉ cần dán vào phụ lục. Đây là lỗi 5 phút, không phải lỗi cần chạy lại mô hình.
- Năm ngành hiện mất tích khỏi bài: Chemicals (−1,73%), Stone/glass/base metals (−2,32%), Agro-food (+2,04%), Minerals & fuels (+0,18%), Wood/pulp/paper (+3,00%).

### A6. Không có Figure A1

- Đánh số nhảy từ `Figure 4` sang `Figure A2`. Đổi `A2` → `A1`, hoặc tạo A1 (gợi ý dùng cho scatter ở [C4](#c4-tuyên-bố-quan-hệ-monotonic-mà-không-có-thước-đo)).

### A7. Bảng Appendix nằm giữa thân bài

- **Dòng:** 100 (A2), 121 (A3), 232 (A4) → chuyển xuống Appendix, thân bài chỉ để chỉ dẫn chiếu.

### A8. "six stages" nhưng có 7 tiểu mục

- **Dòng:** 31 → `seven stages`.

### A9. Không nhất quán ngôi: "we" vs "Author's calculations"

- Thân bài dùng `we` (7 lần); chú thích nguồn dùng `Author's calculations` — số ít (14 lần). Chọn một.

### A10. Heading ABSTRACT trống

- **Dòng:** 3–4. Viết **sau cùng**. Ba con số không được xuất hiện như phát hiện: `p = 0.202`, `q = 0.228`, `p = 0.978`. Bản cũ lưu ở [Phụ lục](#phụ-lục--abstract-đã-xoá-lưu-để-tham-chiếu).

---

## NHÓM B — MÂU THUẪN SỐ LIỆU

> **Bản 1 liệt kê 7 lỗi ở nhóm này. Sau khi kiểm chứng: 5 lỗi thật, 2 lỗi ma (B4, B7 cũ).**

### B1. Thân bài L148 mâu thuẫn với Table 6

- **Dòng:** 148 vs 188
- **Hiện trạng:**
  - L148: *"The GPR × DTA Depth interaction is −0.0052 (**p < 0.001**)"*
  - L188 (Table 6): `−0.0052 | 0.0017 | −0.52 | 0.007`
- **Con số nào đúng?** → **`p = 0.007` đúng.** Đã kiểm với đầy đủ độ chính xác từ `step13b_hs2_survival_interactions.csv`:

  ```
  est = -0,0052347633308720398     SE = 0,00168413530871193     t = -3,108280
  fixest báo cáo        p = 0,0071945060
  t(df = 15)         -> p = 0,0071945060   ← KHỚP CHÍNH XÁC
  phân phối chuẩn    -> p = 0,0018820
  Số cluster: năm = 16, cặp = 12.436  →  df = min(16 ; 12.436) − 1 = 15
  ```

- **⚠️ CẢNH BÁO — bản 1 sai ở đây.** Bản 1 tính `p` bằng phân phối chuẩn, ra `0.00222`, rồi kết luận "cả hai đều sai" và đề xuất **sửa SE thành `0.0019`**. Điều đó **sai**: `feols` của fixest dùng phân phối **t**, không phải chuẩn, và với two-way clustering nó đặt `df = số cluster nhỏ nhất − 1 = 15`. SE `0.0017` và p `0.007` hoàn toàn nhất quán với nhau. Sửa SE sẽ đưa một con số sai vào bảng đang đúng.
- **Sửa:** Chỉ sửa **L148**: `p < 0.001` → `p = 0.007`. Không đụng vào bảng.
- **Liên quan:** hệ quả sâu hơn của việc `df = 15` nằm ở [G2](#g2-quy-ước-inference-trộn-lẫn-và-không-được-khai-báo).

### B2. Câu robustness nói sai sự thật về chính bảng của nó ✅ *(đã kiểm — đúng là lỗi)*

- **Dòng:** 179
- **Hiện trạng:** *"Alternative GPR measures – the threat component, the **acts component**, the log-transformed mean, and the annual peak – **all** produce negative and **significant** depth interactions..."*
- **Kiểm chứng lại từ CSV:**

  ```
  GPR threats          p = 0,002   có ý nghĩa
  Log annual mean GPR  p = 0,008   có ý nghĩa
  Annual peak GPR      p = 0,007   có ý nghĩa
  GPR acts             p = 0,229   ← KHÔNG có ý nghĩa
  ```

- **Dấu hiệu làm reviewer chú ý:** phần ngoặc đơn liệt kê threat, peak, log-mean và **bỏ acts ra**. Người viết biết acts không đạt nhưng vẫn viết "all".
- **Sửa:** *"**three of the four** alternative measures produce negative and significant depth interactions"*, rồi biến điểm yếu thành bằng chứng ủng hộ cơ chế:

  > *"The acts component is the exception (−0.37 pp, p = 0.229). This is consistent with, rather than contrary to, the option-value mechanism: the acts index records geopolitical events that have already materialised, whereas the threats index captures anticipated risk. A mechanism operating through the option value of waiting should respond to expectations of future disruption, not to realised events. The pattern of significance across the two components is therefore what the mechanism predicts."*

### B3. Panel C của Table 6 không được nhắc một chữ nào trong thân bài ✅ *(đã kiểm — đúng là lỗi)*

- **Dòng:** 196–197
- **Hiện trạng:** `| C. Active-FTA-only sample | −0.0046 | 0.0031 | −0.46 | 0.162 | 3,479,262 |`
- **Vấn đề:** Đoạn L179 thảo luận Panel A và B rồi dừng. Panel C — kiểm định **không đạt ý nghĩa** — bị bỏ qua hoàn toàn.
- **Vì sao đây là điểm nghiêm trọng hơn bản 1 nghĩ:** đây là đặc tả **sạch nhất về mặt nhận diện** cho hiệu ứng depth (đo depth *trong* nhóm đã có FTA, không lẫn với biến thiên FTA/non-FTA). Việc nó không đạt ý nghĩa là thông tin cốt lõi, không phải chú thích.
- **Kiểm chứng:** `3.479.262 / 8.045.131 = 43,25%` → giảm **56,8%**. Con số 57% là chính xác.
- **Sửa:**

  > *"Restricting the sample to pairs with an active FTA leaves the point estimate essentially unchanged (−0.46 pp) but inflates the standard error, so that significance is lost (p = 0.162). The loss of precision is expected: this restriction removes the non-FTA comparison group that supplies most of the identifying variation in the interaction term, and reduces the sample by 57 percent. The stability of the point estimate, rather than its significance in this subsample, is the informative result."*

### ~~B4 (cũ). Hai trong mười bốn điều khoản không thuộc bundle nào~~ → **LỖI MA, ĐÃ HUỶ**

Bản 1 khẳng định 5 bundle chỉ chứa 12 điều khoản, competition policy không thuộc bundle nào, và đề xuất **thêm bundle thứ 6**. Kiểm tra trực tiếp `python/12a_build_hs2_mechanism_panel.py:108-135`:

| Bundle | Điều khoản trong code | Số |
|---|---|---|
| `border_coordination` | Customs, SPS, TBT | 3 |
| `investment_production` | Investment, TRIMs, **CompetitionPolicy**, MovementofCapital | 4 |
| `digital_knowledge` | DataProtection, InformationSociety, ResearchandTechnology, InnovationPolicies, **IPR**, **TRIPs** | 6 |
| `services_procurement` | GATS, PublicProcurement | 2 |
| `environmental` | EnvironmentalLaws | 1 |
| **Tổng** | | **16** |

Có **16** điều khoản (`SELECTED_MECHANISMS` ở `06_build_dta_pair_year_panel.py:73-90`), và **cả 16 đều thuộc bundle**. Competition policy nằm trong `investment_production`. Cả hai biến IPR đều nằm trong `digital_knowledge`.

**Vì sao Table A3 chỉ có 14?** Code ghi rõ ở `r/12c_individual_dta_provision_screen.R:11-14` và có file audit chứng minh (`outputs/audit/step12c_individual_provision_support.csv`): ngưỡng support **pre-specified 500 cặp**; `InformationSociety` (287 cặp) và `InnovationPolicies` (29 cặp) bị loại. **Đây là thực hành tốt, không phải lỗi.**

**→ Thay bằng B4 mới dưới đây.**

### B4 (mới). Mô tả bundle trong bài liệt kê thiếu 4 trong 16 điều khoản

- **Dòng:** 97
- **Hiện trạng:** *"(i) Border Coordination (customs, SPS, TBT); (ii) Investment and Production (investment, capital mobility, TRIMS); (iii) Services and Procurement (trade in services, public procurement); (iv) Environmental Provisions (environmental laws); and (v) Digital and Knowledge (data protection, IPR, research and technology)."* → tổng cộng **12**.
- **Thiếu so với code:** `CompetitionPolicy` (bundle ii), `InformationSociety`, `InnovationPolicies`, `TRIPs` (bundle iii… v).
- **Hệ quả:** vì bài liệt kê thiếu competition policy, mục 4.3.2 (nơi nó là một trong ba "phát hiện") đọc như không nhất quán với mục 4.3.1 — dù code thì hoàn toàn nhất quán.
- **Sửa:** Liệt kê đủ 16 điều khoản ở L97, đúng theo bảng trên. Đồng thời sửa L115 (*"all fourteen individual legally enforceable provisions"*) thành:

  > *"We screen fourteen of the sixteen coded provisions individually. Information society and innovation policies are excluded because their support is too sparse for reliable estimation (287 and 29 unordered pairs respectively, against a pre-specified threshold of 500)."*

- **Ưu tiên:** Trung bình. Là lỗi mô tả, không phải lỗi phân tích. Sửa 10 phút.

### B5. "Environmental bundle" thực chất chỉ chứa 1 điều khoản ✅ *(đã kiểm — đúng là lỗi)*

- **Dòng:** 97, 103 (Table A2), 126 (Table A3)
- **Kiểm chứng lại:** hệ số và SE **trùng khít** hoàn toàn.

  | | Estimate | SE | Effect | Raw p | BH-FDR p |
  |---|---|---|---|---|---|
  | A2 — Environmental provisions (bundle) | 0.0384 | 0.0195 | +3,91% | 0.049 | **0.244** |
  | A3 — Environmental laws (điều khoản) | 0.0384 | 0.0195 | +3,91% | 0.049 | **0.228** |

- **Vấn đề:** Đây không phải bundle, đây là một điều khoản duy nhất được đặt tên như bundle. Trình bày nó là "bundle mạnh nhất" gây nhầm lẫn — nó không cung cấp thông tin nào ngoài A3.
- **Vì sao q khác nhau (0.244 vs 0.228):** family of tests khác nhau — 5 bundle vs 14 điều khoản. **Hợp lý**, nhưng bài phải nói rõ, nếu không sẽ bị đọc là lỗi tính toán. Xem [D5](#d5-không-nêu-family-of-tests-của-bh-fdr).
- **Sửa:** Ghi rõ trong mục 3 và chú thích A2:

  > *"The environmental bundle comprises a single provision (environmental laws); its coefficient is therefore identical to the corresponding row of Table A3, and it is retained in the bundle table only for completeness of the thematic classification."*

### B6. Clustering được mô tả khác nhau ở 4 chỗ ✅ *(đã kiểm — đúng là lỗi, và đã tìm ra đáp án)*

- **Hiện trạng:**

  | Vị trí | Mô tả trong bài | **Thực tế trong code** |
  |---|---|---|
  | L42 (thân bài 4.1) | *"clustered at the unordered country-pair level, with multiway pair-plus-year reported for robustness"* | Bảng in **pair-plus-year** |
  | Chú thích Table 3 (L61) | *"multiway-clustered"* | ✅ đúng |
  | Chú thích Table 4 (L81) | *"pair-clustered"* | ❌ **SAI** — thực tế là pair-plus-year |
  | Chú thích Table 5, 6, 8 | *"pair-plus-year multiway"* | ✅ đúng |

- **Đáp án dứt điểm:** `r/16_build_paper_tables_figures_FIXED.R` lọc `inference == "pair_plus_year_cluster"` ở **cả 16 chỗ** (dòng 940–2280). **Mọi bảng trong bài đều dùng pair-plus-year.** Đã xác nhận bằng cách đối chiếu giá trị BH-FDR của Table 4 (0.0263, 0.0031…) — chúng khớp đúng hàng `pair_plus_year_cluster` của `step11_hs2_sector_coefficients.csv`.
- **Sửa:**
  1. Sửa chú thích Table 4 (L81): `pair-clustered` → `pair-plus-year multiway clustered`.
  2. Trong mục 3.3.1 nêu **một** chiến lược mặc định và lý do chọn nó — bắt buộc phải nêu cả `df` (xem [G2](#g2-quy-ước-inference-trộn-lẫn-và-không-được-khai-báo)).
  3. Chuẩn hoá chú thích của cả 6 bảng + 4 hình về cùng một cách diễn đạt.
  4. Nêu rõ FE là **directed pair** (i→j) trong khi clustering là **unordered pair** — không mâu thuẫn, nhưng hiện đọc như mâu thuẫn.

### ~~B7 (cũ). "Fourteen provisions" mâu thuẫn với thang đo depth chạy tới 30~~ → **LỖI MA, ĐÃ HUỶ**

Bản 1 xếp mục này **"Ưu tiên: Cao — có thể khiến toàn bộ Table A4 bị loại"**, với lập luận rằng nếu chỉ có 14 điều khoản thì báo cáo hiệu ứng ròng tại 20 và 30 là ngoại suy ngoài miền dữ liệu.

Kiểm tra trực tiếp trên panel parquet:

```
                              max depth    ≥20 điều khoản    ≥30 điều khoản
recovery (Table 7 / A4)        38 prov         4,37%             3,41%
survival (Table 5)             38 prov        12,83%            10,89%
PPML     (Table 3)             38 prov         8,19%             6,89%
```

Thang depth chạy tới **38** điều khoản (khớp `agent.md`: *"0.0 → 3.8, tương ứng tối đa 38 điều khoản"*). Các hàng 20 và 30 của Table A4 **nằm trong miền dữ liệu**. Không có ngoại suy. **Không được xoá hàng nào.**

**→ Thay bằng B7 mới dưới đây.**

### B7 (mới). Chữ "provisions" mang hai nghĩa khác nhau, không chỗ nào phân biệt

- **Dòng:** 115, 148, 175, 232 + các hàng Table A4
- **Vấn đề thật:** bài dùng cùng một từ cho hai khái niệm:
  - **38** = tổng số legally enforceable provisions dùng để tính `DTA Depth` (chia 10)
  - **14** = số điều khoản được **screen riêng lẻ** ở Table A3 (14 trong 16 điều khoản được code, 2 bị loại vì sparse support)
- Người đọc gặp "fourteen provisions" ở L115 rồi gặp "30 provisions" ở Table A4 sẽ kết luận sai rằng bài đang ngoại suy — đúng như bản 1 đã kết luận sai.
- **Sửa:** Trong mục 3.2 tách bạch tường minh:

  > *"`DTA Depth` is the count of legally enforceable provisions in the agreements in force for a pair, divided by ten. In the estimation sample it ranges from 0 to 38 provisions, with a median of 12 among pairs with an active FTA. This is distinct from the fourteen provisions screened individually in Table A3, which are the subset of coded provision categories with sufficient support for separate estimation."*

- **Ưu tiên:** Trung bình (lỗi thuật ngữ, không phải lỗi phân tích).

---

## NHÓM C — OVERCLAIM: DIỄN GIẢI VƯỢT QUÁ BẰNG CHỨNG

> **Toàn bộ nhóm này đã được kiểm lại bằng CSV gốc và giữ nguyên hiệu lực. Đây vẫn là nhóm quan trọng nhất.**

**Nguyên tắc chi phối:** một bài có kết quả null hoặc ngược kỳ vọng chỉ được đăng khi nó **thận trọng một cách nhất quán**. Overclaim ở giữa bài rồi hedge ở Abstract là mẫu hình khiến reviewer mất niềm tin vào mọi con số còn lại.

**Vấn đề hệ thống:** bài **tự áp dụng** hiệu chỉnh Benjamini–Hochberg ở mục 3.3.3, rồi lại diễn giải các hệ số **không** qua được FDR như phát hiện chắc chắn. Đây là double standard, và reviewer sẽ coi đó là lỗi nghiêm trọng hơn bản thân kết quả null.

### C1. Diễn giải hệ số p = 0.202 như một cơ chế đã được thiết lập

- **Dòng:** 45
- **Hiện trạng:** *"Although the depth coefficient does not reach conventional significance, its sign reversal in the joint specification is economically informative: conditional on having an FTA, deeper institutional commitments **partially offset** the heightened vulnerability... This decomposition **reveals a nuanced mechanism**... deeper legal frameworks **provide partial institutional insurance**."*
- **Bằng chứng (đã kiểm):** Table 3 cột (3): `GPR × DTA depth = +0.0099 (SE 0.0078), p = 0.202`.
- **Điểm nặng thêm sau khi kiểm code:** hệ số này đến từ một đặc tả có **đa cộng tuyến nặng**. File audit của chính dự án (`outputs/audit/step12a_mechanism_correlations.csv`) cho `corr(depth_strict_l1_10, fta_active_l1) = 0,734`. Đó là lý do hệ số depth lật dấu từ −0.0053 (đơn lẻ) sang +0.0099 (joint), và hệ số FTA nhảy từ −0.0241 sang −0.0382. Script `12b` thậm chí có comment nói rõ *"Do NOT put all five bundles in one regression"* vì đúng lý do này — nhưng logic đó không được áp cho spec joint FTA+Depth chính.
- **Sửa:**

  > *"The depth interaction reverses sign in the joint specification, but the coefficient is not statistically distinguishable from zero (p = 0.202) and we therefore draw no inference from it. The reversal should in any case be read with caution: the FTA indicator and the depth measure are correlated at 0.73 in the estimation sample, so the two interaction terms are not separately well identified. We note the sign only because it is what a partial-offsetting mechanism would predict, and because the same coefficient becomes positive and significant under country-specific risk measures (Table 8, Panel A) — a pattern we return to in Section 4.6."*

- **Vì sao cách này tốt hơn:** nó *bảo lưu* luận điểm cho mục 4.6 (nơi bạn thật sự có `+2,84%`, `p = 0.018`), thay vì đốt nó ở đây trên một hệ số ns.

### C2. Toàn bộ mục 4.3 xây trên một tiền đề chưa được thiết lập

- **Dòng:** 93
- **Hiện trạng:** *"This analysis directly addresses the question of **why** deeper agreements partially offset the FTA vulnerability..."*
- **Vấn đề:** Chữ "**why**" tiền giả định hiện tượng đó *đã* được chứng minh. Nhưng Table 3 chỉ cho `p = 0.202`. Đây là lỗi cấu trúc — nó làm cả mục 4.3 (dòng 91–142, gồm hai bảng) mất nền móng.
- **Sửa:** Đổi từ "why" sang "whether":

  > *"We now ask **whether** any specific institutional provisions display shock-absorbing properties, and if so which. This is an exploratory exercise: the aggregate depth interaction in Table 3 is not statistically significant, so the analysis below is a search for candidate mechanisms rather than a decomposition of an established effect."*

### C3. Tuyên bố nhận diện nhân quả từ dị biệt theo ngành

- **Dòng:** 69
- **Hiện trạng:** *"The monotonic relationship between sectoral GVC complexity and the magnitude of the GPR × FTA coefficient **provides strong evidence that supply-chain interdependence is the causal pathway, not reverse causality or omitted confounders**."*
- **Vấn đề:** Dị biệt theo ngành **không phải** chiến lược nhận diện nhân quả. Nó loại trừ một số giải thích thay thế nhưng không loại trừ được biến bỏ sót có tương quan với độ phức tạp ngành (thâm dụng tín dụng, tính chu kỳ, tập trung địa lý). Đây là câu reviewer đánh dấu đỏ đầu tiên.
- **Sửa:**

  > *"This cross-sectoral gradient is **consistent with** the supply-chain interdependence channel and is difficult to reconcile with explanations that operate uniformly across products, such as reverse causality in agreement formation. It is not, however, a causal identification strategy: sectors that are more GVC-complex also differ in credit intensity, cyclicality, and geographic concentration, any of which could generate a similar gradient."*

### C4. Tuyên bố quan hệ "monotonic" mà không có thước đo

- **Dòng:** 69
- **Vấn đề:** Bài **không có thước đo định lượng nào** về GVC complexity. Xếp 5 ngành theo hệ số rồi gọi là "monotonic" là lập luận vòng tròn: định nghĩa complexity bằng chính hệ số muốn giải thích.
- **Sửa — hai lựa chọn:**
  - **(a) Nhanh:** `monotonic` → `graded` / `ordered`, mô tả gradient bằng ngôn ngữ định tính.
  - **(b) Có giá trị cao nhất trong toàn bộ danh sách này:** xây chỉ số complexity **độc lập** với hệ số, vẽ scatter *hệ số ngành × chỉ số* và báo cáo tương quan Spearman. Nguồn: **Rauch (1999)** homogeneous/reference-priced/differentiated; **Nunn (2007)** contract intensity; **Antràs & Chor (2013)** upstreamness.
  - Nếu làm (b): dùng cho **Figure A1** đang thiếu ([A6](#a6-không-có-figure-a1)). Với 10 ngành (đã có đủ trong `appendix_table_a1_full_sector_results.csv`), một tương quan Spearman có ý nghĩa sẽ chuyển C3 và C4 từ điểm yếu thành điểm mạnh nhất về cơ chế của bài.

### C5. "Coherent micro-mechanism" từ ba hệ số không qua được FDR

- **Dòng:** 119
- **Hiện trạng:** *"Collectively, these provision-level results **reveal a coherent micro-mechanism**: the partial offsetting effect of DTA depth... **is driven by** specific institutional disciplines..."*
- **Bằng chứng (đã kiểm lại từ `appendix_table_a3_individual_provisions.csv`):**

  | Điều khoản | Estimate | Raw p | **BH-FDR q** |
  |---|---|---|---|
  | Competition policy | 0.0353 | 0.037 | **0.228** |
  | Environmental laws | 0.0384 | 0.049 | **0.228** |
  | Research and technology | 0.0343 | 0.041 | **0.228** |

  **Không một điều khoản nào — và không một bundle nào — sống sót qua BH-FDR.** q nhỏ nhất trong toàn bộ Table A2 là 0.244; trong A3 là 0.228. Cả hai đều xa ngưỡng 10% mà bài tự đặt ra ở mục 3.3.3.
- **Ghi nhận:** code hoàn toàn đúng — nó tính, xuất cả p thô lẫn q, và **không gắn sao** vào A2/A3. Lỗi chỉ ở tầng viết.
- **Sửa:**

  > *"Three provisions — competition policy, environmental laws, and research and technology cooperation — show raw p-values below 0.05. **None survives Benjamini–Hochberg correction across the fourteen tests (q = 0.228 for all three).** With fourteen simultaneous tests, obtaining three nominal rejections at the 5% level is close to what chance alone would deliver. We therefore treat these provisions as **hypotheses for future work rather than established channels**, and note that the pattern — all three are behind-the-border disciplines, while none of the border-focused provisions (customs, SPS, TBT) or investment chapters shows any effect — is the reason they merit a targeted follow-up design."*

- **Đồng thời sửa:** ba đoạn L116–118 hiện diễn giải cơ chế từng điều khoản rất tự tin (*"ensuring a level playing field"*, *"paradoxically anchoring trade relationships"*, *"enhances firms' adaptive capacity"*). Giữ nội dung, chuyển sang thể điều kiện (`would`, `could`, `a possible interpretation is`).

### C6. Diễn giải một hệ số p = 0.978 thành hiệu ứng có hướng

- **Dòng:** 216
- **Hiện trạng:** *"However, over a two-year horizon, these same institutional frameworks **facilitate re-engagement**... The result is not permanent hysteresis but rather a transitory adjustment cost that the institutional infrastructure of deep agreements **eventually overcomes**."*
- **Bằng chứng (đã kiểm):** Table 7, re-entry 2 năm, directed-pair FE: `+0.0001 (SE 0.0035), p = 0.978`.
- **Vấn đề:** `p = 0.978` là một số zero được ước lượng rất chính xác. Nó **không** nói thể chế thúc đẩy tái gia nhập; nó nói **không có hiệu ứng nào cả**.
- **Sửa — và lưu ý kết luận đúng vẫn là kết luận tốt:**

  > *"At the two-year horizon the interaction is precisely estimated at zero (+0.0001, p = 0.978), and the full-recovery outcomes are likewise indistinguishable from zero at both horizons. **We therefore find no evidence of permanent hysteresis**: the depth-related friction we detect at the one-year horizon does not persist. We emphasise that this is an absence of a detected effect, not evidence that deep agreements actively accelerate re-entry — our data cannot distinguish the two."*

- **Điểm cần thấy:** "Không có hysteresis vĩnh viễn" là phát hiện hợp lệ và công bố được. "Thể chế giúp tái gia nhập" là tuyên bố bịa từ số zero. Bạn không mất gì khi sửa.

### C7. Cùng lỗi C6, lặp lại ở mục tổng hợp cơ chế

- **Dòng:** 303
- **Hiện trạng:** *"...**the institutional infrastructure of deep agreements facilitates re-entry over a two-year horizon**, converting what would otherwise be permanent trade destruction into a transitory adjustment."*
- **Nghiêm trọng hơn C6** vì đây là mục 4.7 — phần reviewer đọc để nắm luận điểm cuối cùng.
- **Điểm yếu thứ hai chưa được thừa nhận ở đâu (đã kiểm lại từ `table7_post_exit_recovery.csv`):**

  | Outcome | directed-pair FE | pair–HS2 FE |
  |---|---|---|
  | Re-entry trong 1 năm | **−0.0035\*\*** (p = 0.044) | **−0.0001** (ns) |

  Kết quả recovery duy nhất có ý nghĩa của bài **không ổn định với đặc tả FE**. Bài hiện trình bày hai đặc tả cạnh nhau trong Table 7 mà không bình luận gì.
- **Sửa:** Viết lại 4.7.3 theo C6, và thêm:

  > *"We note that the one-year re-entry result is sensitive to the fixed-effects specification: it is significant under directed-pair fixed effects (−0.35 pp, p = 0.044) but collapses to −0.01 pp under pair–HS2 fixed effects. We therefore treat the recovery evidence as weak, and rest the paper's extensive-margin conclusions on the survival results, which are stable across all specifications we examine."*

---

## NHÓM D — THIẾU SÓT NỘI DUNG

Những thứ **chưa tồn tại** trong file. Toàn bộ thuộc mục 3 (hiện trống).

### D1. Không có định nghĩa "hàng trung gian"

Đây là biến phụ thuộc của toàn bộ bài, và file hiện **không nhắc đến cách xác định nó ở đâu**.

**Đã có sẵn trong code** (`python/04_finalize_sample_and_bec_map.py`, `python/05_build_positive_trade_aggregates.py`): bảng tương quan **UN BEC Rev.4 → HS2007**, lọc các mã BEC `111, 121, 21, 22, 31, 322, 42, 53`. Kết quả lưu ở `data/interim/hs07_bec4_clean_map.csv`. Phân loại ở cấp **HS6** rồi mới cộng lên HS2 (không phải gán nhãn cả chương HS2) — đây là chi tiết cần nêu vì nó trả lời trước câu hỏi hiển nhiên của reviewer.

Cần nêu: bảng phân loại nào, mã cụ thể nào, và ánh xạ HS6 → HS2 thực hiện ra sao.

### D2. Không nêu cách xử lý zero trade

**Đã có sẵn số liệu:** mẫu PPML có **47,52%** dòng zero (7.961.379 / 16.752.461). Cách xây dựng là **support panel** (`python/08_build_estimation_panels.py:541-548`): giữ mọi nhóm pair–HS2 có ít nhất một năm dương, rồi điền đủ zero cho mọi năm trong nhóm đó. Nhóm zero ở **mọi** năm bị loại vì pair–HS2 FE hấp thụ hoàn toàn, không đóng góp thông tin nhận diện.

Đây là lựa chọn đúng và cần được nêu tường minh — nó vừa biện minh việc dùng PPML, vừa phòng thủ trước câu hỏi "sao không phải 25.440 × 88 × 17 dòng".

### D3. Không mô tả thiết kế phân tích recovery

Mục 4.5 dùng 1.151.310 exit events nhưng không định nghĩa. **Đáp án đã có trong code** (`python/14a_build_post_exit_recovery_panel.py`):

- **Exit event:** trade dương ở `t−1` và bằng 0 ở `t`, ở cấp pair–HS2. Chỉ cần 1 năm zero.
- **Full recovery:** `trade(t+1) ≥ trade(t−1)` — tức hồi về **100%** giá trị trước exit, **theo giá danh nghĩa** (không khử lạm phát — cần nêu là hạn chế).
- **Vì sao N giảm 1.151.310 → 1.064.542:** exit năm 2022 không quan sát được `t+2`. Đúng như bản 1 đoán.
- **Vì sao hai đặc tả FE:** cần giải thích, và **directed-pair không nên là "primary"** — xem [C7](#c7-cùng-lỗi-c6-lặp-lại-ở-mục-tổng-hợp-cơ-chế).

### D4. Không mô tả mẫu con 946 cặp

Con số 946 chỉ xuất hiện một lần (L259). **Đã có file audit đầy đủ:** `outputs/audit/step15b_country_gpr_sample_coverage.csv` liệt kê từng nước có/không có chuỗi GPR quốc gia, và `step15b_country_gpr_panel_audit.txt` ghi rõ *"This is a restricted-sample robustness check, not a replacement for the global-GPR baseline."*

Mẫu giảm từ 12.720 xuống **946** cặp không thứ tự (7,4%), từ 16,75M xuống 2,52M dòng (15%). Cần nêu ở mục 3: vì sao GPR quốc gia chỉ có cho một nhóm nước, những nước nào, và mẫu con khác mẫu đầy đủ ra sao về cơ cấu.

### D5. Không nêu family of tests của BH-FDR

Reviewer sẽ hỏi chính xác câu này. **Đáp án đã xác minh bằng cách tự tính lại BH từ p thô:**

| Bảng | Family | Nhóm theo |
|---|---|---|
| Table 4 / A1 | **10 ngành**, áp riêng cho FTA và cho Depth | `by = .(model, inference)` — `r/11:578` |
| Table A2 | **5 bundle**, áp riêng cho standalone và FTA-conditional | `by = .(model_spec, inference)` — `r/12b:572` |
| Table A3 | **14 điều khoản** | `by = inference` — `r/12c:578` |

Đã kiểm chứng: tự tính BH với n=10 cho từng `model` khớp chính xác cột `p_value_fdr_bh` của step11; gộp cả 20 test thì **không** khớp. Tức family đúng là 10, không phải 20.

**Lưu ý cần nêu:** nếu gộp 20 test cho Table 4 thì Machinery (q = 0.0765) và Transport-depth (q = 0.0615) sẽ rơi khỏi ngưỡng 10%. Việc tách hai family là lựa chọn hợp lý nhưng **phải được nói ra**.

Đây cũng là điều giải thích vì sao environmental có `q = 0.244` ở A2 và `q = 0.228` ở A3 (xem [B5](#b5-environmental-bundle-thực-chất-chỉ-chứa-1-điều-khoản)).

### D6. Không có mục "Identification concerns"

Bốn điểm cần phòng thủ **chủ động**. Nêu trước khi reviewer nêu sẽ ghi điểm lớn:

1. **Nội sinh của DTA depth.** Các nước chọn ký hiệp định sâu không ngẫu nhiên, và cùng những yếu tố đó có thể quyết định độ nhạy với sốc. Hướng khắc phục: đo `Depth` tại năm ký kết (pre-determined); loại các cặp có thay đổi depth trong kỳ; hoặc event-study quanh năm hiệu lực. Trích Baier & Bergstrand (2007).

2. **LPM cho biến nhị phân với FE 4 chiều.** Cần biện minh so với discrete-time hazard hoặc Cox (Besedeš & Prusa). Tối thiểu: **báo cáo tỷ lệ fitted values nằm ngoài [0,1]**. Tỷ lệ sống sót nền là 84,94% — khá xa 0 và 1, nên LPM có thể bảo vệ được, nhưng phải có con số.

3. **Incidental parameter bias trong PPML bốn chiều.** Trích **Weidner & Zylkin (2021)**: PPML vẫn nhất quán nhưng khoảng tin cậy không đặt đúng tâm và cluster-robust SE bị chệch trong panel T cố định. Nêu chủ động sẽ ghi điểm lớn, và liên quan trực tiếp đến [G2](#g2-quy-ước-inference-trộn-lẫn-và-không-được-khai-báo).

4. **GPR toàn cầu là biến chung.** Nêu **ưu điểm** (ngoại sinh với mọi cặp — không cặp nào gây ra GPR toàn cầu) và **nhược điểm** (không có biến thiên chéo, hiệu ứng chính bị FE thời gian hấp thụ hoàn toàn, nên **toàn bộ nhận diện đến từ số hạng tương tác**). Đây là thiết kế **difference-in-differences liên tục**. Điểm này hiện chưa nêu ở đâu và là đặc điểm nhận diện quan trọng nhất của bài.

### D7. Không dẫn chiếu văn liệu survival

Kết quả **mạnh nhất và ổn định nhất** của bài ở biên mở rộng (Table 5, 6, Figure 3, 4), nhưng bài không trích tài liệu nào về sống sót quan hệ thương mại. Bắt buộc có: **Besedeš & Prusa (2006a, 2006b)**, **Nitsch (2009)**.

### D8. REFERENCES trống

Đang trích trong mục 4 và **phải** có: Anderson & van Wincoop (2003); Head & Mayer (2014); Caldara & Iacoviello (2022); Antràs (2003); Antràs & Helpman (2004); Horn, Maggi & Staiger (2010); Benjamini & Hochberg (1995); Santos Silva & Tenreyro (2006).

Bổ sung tối thiểu theo nhóm:

- **Gravity/PPML:** Correia, Guimarães & Zylkin (2020) `ppmlhdfe`; Weidner & Zylkin (2021); Yotov, Piermartini, Monteiro & Larch (2016); Baier & Bergstrand (2007); Cameron, Gelbach & Miller (2011)
- **Deep trade agreements:** Hofmann, Osnago & Ruta (2017); Mattoo, Rocha & Ruta (2020); Laget, Osnago, Rocha & Ruta (2020); Fernandes, Rocha & Ruta (2021)
- **Bất định & hysteresis:** Dixit (1989); Handley & Limão (2017); Handley (2014); Baldwin & Krugman (1989)
- **GVC / hợp đồng / tính đặc thù:** Nunn (2007); Rauch (1999); Antràs & Chor (2013); Levchenko (2007)
- **Sống sót quan hệ thương mại:** Besedeš & Prusa (2006a, 2006b); Nitsch (2009)
- **Phân mảnh địa kinh tế:** Aiyar et al. (2023, IMF); Góes & Bekkers (2022, WTO)

> **Cảnh báo:** kiểm tra lại năm và thông tin xuất bản của **từng** mục trước khi nộp. Không trích theo trí nhớ, và không tin công cụ AI về *nội dung* của một bài báo cụ thể. Lỗi kiểu "trích đúng tên tài liệu nhưng sai nội dung nó nói gì" là loại lỗi không công cụ nào bắt được — ví dụ Baldwin & Taglioni (2006) *"Gravity for dummies and dummies for gravity equations"* là bài về **kỹ thuật ước lượng gravity**, không phải về option value hay sunk cost; option value phải trích Dixit (1989) và Handley & Limão (2017).

---

## NHÓM G — LỖI TẦNG CODE

> **Nhóm mới. Bốn lỗi này không thể phát hiện bằng cách đọc `results.md` — chỉ lộ ra khi chạy lại code và dữ liệu.**

### G1. 🔴 Toàn bộ khoảng tin cậy của mô hình LPM đều quá hẹp

- **Vị trí:** `r/16_build_paper_tables_figures_FIXED.R` hardcode `1.96 * std_error` ở **10 chỗ** (dòng 1157, 1173, 1584, 1592, 1792, 1800, 2148, 2153, 2162, 2167); tương tự trong `10b`, `13b`, `14b`.
- **Vấn đề:** p-value của mô hình LPM được fixest tính từ phân phối **t** với df rất nhỏ, nhưng CI lại dùng phân vị **chuẩn** 1,96. Hai thứ không nhất quán với nhau.

  ```
  step13b (LPM)  : p-dist = t(15)    CI dùng 1,9600   ĐÚNG phải là 2,1314   ← LỆCH
  step13c (jack) : p-dist = t(14)    CI dùng 1,9600   ĐÚNG phải là 2,1448   ← LỆCH
  step14b (2 năm): p-dist = t(13)    CI dùng 1,9600   ĐÚNG phải là 2,1604   ← LỆCH
  step10b (PPML) : p-dist = normal   CI dùng 1,9600   ĐÚNG là 1,9600        ✅ OK
  ```

- **Hệ quả:** mọi "95% CI" của mô hình LPM thực chất là CI **~91,4%**. Ảnh hưởng trực tiếp tới:
  - dải bóng của **Figure 4** (leave-one-year-out)
  - **Table A4** (net effects theo depth)
  - hình marginal-effect (xem [G3](#g3--hai-hình-trong-bài-không-có-code-sinh-ra))
- **Sửa:** thay `1.96` bằng `qt(0.975, df)` với `df` lấy từ chính đối tượng model, rồi vẽ lại Figure 4 và tính lại Table A4. Không ảnh hưởng bảng PPML.

### G2. 🔴 Quy ước inference trộn lẫn và không được khai báo

- **Phát hiện:** kiểm mọi p-value `pair_plus_year_cluster` trong 9 file CSV xem khớp phân phối nào:

  | File | Mô hình | Phân phối | df |
  |---|---|---|---|
  | step10b, step11, step12b, step12c | `fepois` (PPML) | **normal (z)** | ∞ |
  | step13b | `feols` (LPM full) | **t** | **15** |
  | step13c (jackknife) | `feols` | **t** | **14** |
  | step14b (recovery 1 năm / 2 năm) | `feols` | **t** | **14 / 13** |

- **Đây không phải bug** — đó là hành vi chuẩn của fixest (`fepois`→z, `feols`→t với df điều chỉnh theo cluster). Nhưng bài chỉ ghi "multiway clustered" ở **mọi** chú thích, không nơi nào nói phân phối tham chiếu là gì.
- **Vì sao quan trọng:** với two-way clustering, fixest đặt `df = min(số cluster hai chiều) − 1`. Chiều `year` chỉ có 16–17 cluster → **toàn bộ inference của Bảng 5, 6, 7, 8 dựa trên phân phối t với 13–15 bậc tự do.** Đây là điểm mong manh nhất về mặt thống kê của cả bài, và hiện không được nêu ở đâu.
- **Bằng chứng thêm về tính bất ổn:** ở Table 3 (PPML), SE two-way **nhỏ hơn** SE pair-clustered (0,01067 vs 0,01135) — đi ngược hướng lẽ thường. Ở Table 5 (LPM) thì ngược lại, two-way **lớn hơn** 3–4 lần. Ở kiểm định DDD (`step9b`) việc chọn loại clustering còn **lật kết luận**: pair p = 0.014 → two-way p = 0.116.
- **Sửa — chọn một trong hai:**
  - **(a) Khai báo minh bạch:** thêm vào mục 3.3.1 một câu nêu rõ df và lý do; và nói rõ Table 3 dùng z (PPML) còn Table 5–8 dùng t.
  - **(b) Mạnh hơn:** báo cáo **pair-clustered làm inference chính**, two-way làm robustness; hoặc dùng wild cluster bootstrap trên chiều năm (`fwildclusterboot`, hoặc `fixest::boot()`). Cách này miễn nhiễm với vấn đề ít cluster và sẽ dập tắt phản biện.

### G3. 🔴 Hai hình trong bài không có code sinh ra

- `outputs/paper_outputs/figures/figure5_marginal_effect_survival.png`
- `outputs/paper_outputs/figures/figure6_gpr_time_series.png`

Cả hai:
- **không script nào** trong `r/` hay `python/` tạo ra (grep toàn repo: 0 kết quả)
- **không nằm trong** `paper_output_manifest.csv` (manifest chỉ liệt kê 10 file hình)
- **không có** file `figure_data/*.csv` tương ứng

**"Figure 3" của `results.md`** (L166 — hình marginal effect theo depth, nguồn của claim "**more than 12 enforceable provisions**" ở L175) chính là `figure5`. Nghĩa là con số 12 hiện **không truy vết được**: không code, không dữ liệu, không manifest.

- **Liên quan:** nếu sửa lỗi [G1](#g1--toàn-bộ-khoảng-tin-cậy-của-mô-hình-lpm-đều-quá-hẹp), CI rộng ra → ngưỡng "có ý nghĩa thống kê" sẽ **dịch lên cao hơn 12**.
- **Ngưỡng đảo dấu thì tính được và đúng:**

  ```
  ∂S/∂GPR = +0,28 − 0,52 × (D/10)  [pp]
  Bằng 0 tại:  D = 0,28/0,52 × 10 = 5,38  →  ≈ 5,4 điều khoản
  ```

- **Sửa:** viết script sinh ra hai hình này (thêm vào `16_build_paper_tables_figures_FIXED.R`), xuất kèm `figure_data` CSV, dùng `qt(0.975, df)` cho dải CI, rồi **tính lại ngưỡng 12** từ output thật. Nếu không làm được, phải xoá claim "more than 12 provisions" khỏi L175.

### G4. 🟡 Repo không chạy được ở trạng thái hiện tại

- **32/33 script** hardcode `PROJECT_ROOT = "H:/AIID_DTA_GPR"`, trong khi workspace thật là `D:\uni\AIID\AIID_DTA_GPR`.
- **16/16 script R** gọi `install.packages()` lúc runtime → phiên bản package có thể khác mỗi lần chạy. Không có `renv.lock` / `requirements.txt`.
- **`r/16_build_paper_tables_figures.R` là bẫy:** chỉ 10 dòng, chỉ chứa `install.packages()`. File thật là `..._FIXED.R` (3.089 dòng). Nên đổi tên thành `00_install_packages.R`.
- **5 cặp file `_FIXED` / bản gốc** không đánh dấu bản nào canonical. Chạy nhầm `13a` bản gốc sẽ ra panel khác.
- **Không có README** — thứ tự chạy chỉ nằm trong `agent.md`, và số thứ tự có gap (không có 09a, 10, 12, 13, 14, 15).
- **Ảnh hưởng tới bài:** nếu tạp chí yêu cầu replication package (ngày càng phổ biến), gói hiện tại **không chạy được trên máy nào khác**. Nên xử lý trước khi nộp bản cuối.

---

## NHÓM E — ĐÃ KIỂM CHỨNG ĐÚNG, KHÔNG CẦN SỬA

Đã chạy lại bằng dữ liệu gốc. Không mất thời gian kiểm lại những mục này.

### E1. Toàn bộ marginal effects đều đúng

Đã tính lại `(exp(β) − 1) × 100` cho mọi hệ số trong Table 3, Table 4, Table 8 và A2/A3. **Tất cả khớp.** Sai lệch duy nhất: Table 4, transport equipment depth `−0.0184` → `−1,828%`, bài in `−1,83%`. Làm tròn, không cần sửa.

### E2. Table A4 nhất quán nội bộ

Bước giảm mỗi 10 điều khoản, đã tính lại từ CSV:

```
Re-entry 1 năm       : -0,3543 / -0,3543 / -0,3544 pp   (Table 7: -0,003543 × 100 = -0,3543)  ✅
Full recovery 1 năm  : -0,0869 mỗi bước                  (Table 7: -0,000869)                  ✅
Re-entry 2 năm       : +0,0097 mỗi bước                  (Table 7: +0,000097)                  ✅
Full recovery 2 năm  : -0,0222 mỗi bước                  (Table 7: -0,000222)                  ✅
```

Bảng được tính đúng tuyệt đối. (Vấn đề "miền giá trị" mà bản 1 nêu là **không có thật** — xem [B7 cũ](#b7-cũ-fourteen-provisions-mâu-thuẫn-với-thang-đo-depth-chạy-tới-30--lỗi-ma-đã-huỷ).)

### ~~E3 (cũ). Ngưỡng đảo dấu của Figure 3~~ → **NHẬN ĐỊNH SAI, ĐÃ SỬA**

Bản 1 xếp mục này vào nhóm "đã kiểm chứng đúng" và kết luận con số "more than 12" là "hợp lý". Thực tế **không kiểm chứng được**: hình sinh ra nó không có code, không có dữ liệu, không có trong manifest. Xem [G3](#g3--hai-hình-trong-bài-không-có-code-sinh-ra).

Phần tính ngưỡng **đảo dấu** ở 5,4 điều khoản thì đúng và vẫn giữ nguyên (xem [F1](#f1-đưa-ngưỡng-54-điều-khoản-vào-bài)).

### E4. Các con số N nhất quán

`16.752.356` (PPML), `8.045.131` (survival), `1.151.310` / `1.064.542` (recovery), `2.520.781` / `1.878.443` (mẫu 946 cặp) — đã đối chiếu với row count panel thật và với `model_audit` của từng bước. **Nhất quán hoàn toàn.**

### E5 (mới). Sao trong Table 4 dùng đúng BH-FDR, không dùng p thô

Đã kiểm cả 10 ô của Table 4: số sao khớp chính xác với cột `BH-FDR p`, không phải `raw p`. Ví dụ Transport equipment depth `−0.0184*` với q = 0.0615 → đúng 1 sao. **Không có lỗi ở đây.**

### E6 (mới). Pipeline dữ liệu chạy lại khớp 100%

Mọi hằng số `EXPECTED_*` hardcode trong script đều đúng khi kiểm lại trên parquet thật: 16.752.461 dòng / 985.562 nhóm pair–HS2 / 12.454 cluster / 17 năm / 88 chương HS2 / 47,52% zero; survival 8.219.579; recovery 1.237.520; country-GPR 2.520.781 với 946 cặp. **Không có lỗi số liệu ở tầng dữ liệu.**

### E7 (mới). Mẫu 160 nước được chọn theo tiêu chí pre-determined

`python/04_finalize_sample_and_bec_map.py:254-259` xếp hạng theo **thương mại trung bình tiền kỳ 2007–2009**, không phải tổng cả kỳ. Điều này tránh selection-on-outcome so với các cú sốc GPR 2014 và 2022. **Đây là điểm mạnh nên nêu ra trong mục 3**, không phải điểm cần sửa.

---

## NHÓM F — CƠ HỘI ĐANG BỎ PHÍ

Không phải lỗi. Là những thứ bài **đã có trong dữ liệu** nhưng chưa dùng.

### F1. Đưa ngưỡng 5,4 điều khoản vào bài

Con số dễ nhớ nhất mà bài có, và đang không được nêu. Nên viết **cả hai** ngưỡng ở mục 4.4.1 và 3.3.2:

> *"The net marginal effect crosses zero at approximately **5.4 enforceable provisions** and becomes statistically distinguishable from zero above roughly **N provisions** (Figure 3). Below the crossing point the binary FTA premium dominates; above it the depth penalty does."*

**Lưu ý:** giá trị `N` phải tính lại từ hình được sinh ra bằng CI đúng — xem [G1](#g1--toàn-bộ-khoảng-tin-cậy-của-mô-hình-lpm-đều-quá-hẹp) và [G3](#g3--hai-hình-trong-bài-không-có-code-sinh-ra). Không dùng con số 12 hiện tại cho tới khi hình được tái tạo.

Bối cảnh hữu ích: median depth trong nhóm có FTA là **12 điều khoản**, nên ngưỡng đảo dấu 5,4 nằm **dưới trung vị** — tức phần lớn các cặp có FTA đã nằm ở vùng hệ số âm. Đây là con số làm cho phát hiện có sức nặng.

### F2. Khai thác phân rã của Table 8 để phòng thủ trước "chỉ là sample selection"

Bài đã có sẵn hàng *Restricted-sample global GPR* — benchmark rất tốt — nhưng chỉ dùng cho một câu mơ hồ ở L260. Phân rã chính xác (đã tính lại):

**Hệ số depth (PPML):**

| Bước | Hệ số | Đóng góp |
|---|---|---|
| Mẫu đầy đủ, global GPR (Table 3, cột 3) | +0.0099 (ns) | — |
| Mẫu 946 cặp, global GPR | +0.0160 (ns) | do **thu hẹp mẫu**: +0.0061 (**34%**) |
| Mẫu 946 cặp, country GPR | +0.0280 (p = 0.018) | do **thước đo shock**: +0.0120 (**66%**) |

→ **Hai phần ba** mức thay đổi — và toàn bộ việc chuyển từ ns sang có ý nghĩa — đến từ **chất lượng đo shock**, không từ thu hẹp mẫu.

**Hệ số FTA (PPML):**

| Bước | Hệ số | Đóng góp |
|---|---|---|
| Mẫu đầy đủ, global GPR | −0.0382 | — |
| Mẫu 946 cặp, global GPR | −0.0617 | thu hẹp mẫu: −0.0235 (**50%**) |
| Mẫu 946 cặp, country GPR | −0.0852 | thước đo shock: −0.0235 (**50%**) |

Viết phân rã này ra sẽ dập tắt phản biện hiển nhiên nhất về mục 4.6. **Ghi nhận:** việc code có sẵn hàng placebo này là thiết kế tốt — nên nói rõ trong bài rằng nó được đưa vào có chủ đích.

### F3. Đặt sự phân kỳ hai biên làm luận điểm trung tâm

Phát hiện có giá trị lý thuyết cao nhất của bài đang nằm chôn trong Table 8:

| | GPR × FTA | GPR × DTA depth |
|---|---|---|
| Panel A — giá trị thương mại (PPML) | −8,17%\*\*\* | **+2,84%\*\*** |
| Panel B — sống sót của link (LPM) | −0,06 pp (ns) | **−0,17 pp\*\*\*** |

**Cùng một biến `Depth`: dương ở biên cường độ, âm ở biên mở rộng.** Chiều sâu thể chế *bảo vệ giá trị của các quan hệ lớn* nhưng *tỉa bớt các quan hệ nhỏ*.

Hiện chỉ được nêu như robustness check. Nên là luận điểm bán bài, vì:

- Biến toàn bộ kết quả "null-leaning" thành phát hiện **tích cực** và có cấu trúc
- **Đúng với dữ liệu** — cả hai hệ số đều có ý nghĩa, không cần overclaim gì
- Cho phép khung khái niệm gọn: *"resilience" không phải khái niệm đơn nhất; nó phụ thuộc vào biên bạn đo*
- Dẫn ra hàm ý chính sách sắc nhất: đánh giá tác động hiệp định chỉ nhìn giá trị thương mại sẽ **bỏ sót** việc mạng lưới đang bị thu hẹp về số quan hệ

**Việc cần làm:** mục 2 thêm giả thuyết riêng (H4); mục 4.6 trình bày như phát hiện chính, không phải phụ lục robustness.

### F4. Dùng mẫu link lớn để định vị hiệu ứng, thay vì chỉ để phòng thủ

Table 6 Panel B cho hệ số nhỏ hơn ~4 lần trên mẫu link lớn (`−0.13` / `−0.14 pp` so với `−0.52 pp`). Bài hiện đọc điều này một cách phòng thủ.

Nhưng đây là **bằng chứng trực tiếp cho cơ chế `selective pruning`** mà mục 4.7.3 nêu: nếu chi phí tuân thủ là **cố định**, hiệu ứng *phải* tập trung ở các link nhỏ, cận biên. Nên viết:

> *"The coefficient falls by roughly three-quarters when the sample is restricted to links above USD 100,000 (−0.13 pp) — exactly the gradient a fixed-compliance-cost mechanism implies, since a fixed cost binds hardest on the smallest links. The effect is concentrated where the mechanism says it should be, while remaining negative and significant even among larger links."*

---

## THỨ TỰ SỬA ĐỀ XUẤT

Overclaim phải sửa **trước** khi viết mục 1, 2, 5 — nếu không các phần mới sẽ tự động thừa hưởng cả bảy lỗi Nhóm C.

| Bước | Việc | Nhóm | Đầu ra |
|---|---|---|---|
| 0 | **Sửa L148** `p < 0.001` → `p = 0.007` | B1 | Lỗi số liệu duy nhất được xoá |
| 1 | Sửa 10 lỗi hình thức. A5 chỉ cần dán CSV đã có sẵn | A1–A10 | Bản sạch hình thức |
| 2 | Sửa mâu thuẫn còn lại: B2 (acts), B3 (Panel C), B4 (liệt kê 16 điều khoản), B5 (bundle 1 phần tử), B6 (chú thích Table 4) | B2–B7 | Mọi con số tự nhất quán |
| 3 | **Sửa 7 overclaim.** Bước quan trọng nhất | C1–C7 | Mục 4 nhất quán với chính các bảng của nó |
| 4 | **Sửa nhân tử CI**, tái tạo Figure 3/5 và 6, tính lại ngưỡng "N provisions" | G1, G3 | Hình và CI đúng, claim truy vết được |
| 5 | Khai báo quy ước inference (hoặc chuyển sang pair-clustered / wild bootstrap) | G2 | Inference phòng thủ được |
| 6 | Tạo Table 1, Table 2 (số liệu đã có ở [A4](#a4-không-có-table-1-và-table-2)) | A4 | Mục 3 có nền dữ liệu |
| 7 | Viết mục 3, gồm Identification concerns | D1–D6 | Methodology hoàn chỉnh |
| 8 | Viết mục 2 với giả thuyết cạnh tranh + H4 | D7, F3 | Lit review khớp kết quả |
| 9 | Viết mục 5, rồi mục 1 | F1–F4 | Conclusion + Introduction |
| 10 | Hoàn thiện References, kiểm từng mục | D8 | Bản đầy đủ |
| 11 | Dọn repo cho replication package | G4 | Gói chạy được trên máy khác |

### Kiểm tra cuối bắt buộc

- [ ] Abstract đã được viết lại (hiện trống — xem [A10](#a10-heading-abstract-trống))
- [ ] Mọi con số trong Abstract và mục 1 xuất hiện **y hệt** trong một bảng nào đó ở mục 4
- [ ] Mọi giả thuyết ở mục 2 được trả lời tường minh ở mục 4 ("H1 is supported / H2 is not")
- [ ] Mọi bảng và hình được dẫn chiếu ít nhất một lần — **và mọi bảng/hình được dẫn chiếu đều tồn tại** (A5)
- [ ] **Mọi hình trong bài đều có script sinh ra nó và file dữ liệu kèm theo** (G3)
- [ ] Mọi **panel** trong mọi bảng được thảo luận, kể cả panel không đạt ý nghĩa (B3)
- [ ] Số mục liên tục, không trùng (A2)
- [ ] Mọi tài liệu trích trong bài có trong References, và ngược lại
- [ ] Nhất quán "we" hay "the author" (A9)
- [ ] Nhất quán cách viết p-value, SE và ký hiệu sao trong chú thích **mọi** bảng (B6)
- [ ] **Phân phối tham chiếu và bậc tự do được nêu rõ ở mục 3.3.1** (G2)
- [ ] **Không hệ số nào có `p > 0.05` được mô tả bằng động từ chỉ hiệu ứng** (`provides`, `facilitates`, `reveals`, `is driven by`, `offsets`) — kiểm tra này bắt tất cả lỗi Nhóm C cùng lúc
- [ ] **Không hệ số nào không qua BH-FDR được trình bày như phát hiện đã thiết lập**

---

## PHỤ LỤC — ABSTRACT ĐÃ XOÁ (LƯU ĐỂ THAM CHIẾU)

Bản Abstract bị xoá khỏi `results.md`, lưu lại nguyên văn. **Lý do lưu:** đây là đoạn văn duy nhất trong toàn bộ bản thảo đọc các bảng số liệu một cách chính xác. Ba chỗ in đậm là ba chỗ nó *nói đúng* trong khi mục 4 nói sai — dùng làm chuẩn khi sửa Nhóm C.

> This study examines whether trade agreements strengthen the resilience of intermediate-goods supply chains under geopolitical risk. It constructs a global exporter–importer–HS2–year panel covering 160 economies and customs territories from 2007 to 2023, with 16.75 million observations. Trade values are estimated using Poisson pseudo-maximum likelihood with directed pair–product, exporter–year, importer–year, and product–year fixed effects. Linear probability models separately evaluate the survival of established trade links and their post-exit recovery. **The results do not support a uniform institutional-buffering effect.** Following a one-standard-deviation increase in global geopolitical risk, FTA-covered intermediate-goods trade displays a 2.38% more negative response than uncovered trade, whereas **legally enforceable agreement depth has no statistically detectable global average association with trade values**. In separate sector-specific specifications, negative FTA and depth interactions are concentrated in textiles and footwear, transport equipment, machinery and electronics, precision and other manufactures, and plastics, rubber, and leather. The most consistent result concerns link continuity: ten additional legally enforceable policy areas are associated with a 0.52-percentage-point lower probability that an existing trade link survives under higher geopolitical risk. This relationship remains negative across alternative shocks, established-link samples, leave-one-year-out estimations, and country-specific risk measures. **Post-exit recovery results are mostly statistically indistinguishable from zero.** The findings indicate that the relationship between institutional depth and geopolitical risk differs across trade values and link continuity. Deep integration therefore does not automatically translate into supply-chain resilience.

**Đối chiếu: Abstract nói đúng ở đâu, mục 4 nói sai ở đâu**

| Chủ đề | Abstract (đúng) | Mục 4 (sai) | Số thực tế |
|---|---|---|---|
| Depth ở intensive margin | *"no statistically detectable global average association"* | L45: *"provide partial institutional insurance"* ([C1](#c1-diễn-giải-hệ-số-p--0202-như-một-cơ-chế-đã-được-thiết-lập)) | +0.0099, **p = 0.202** |
| Recovery 2 năm | *"mostly statistically indistinguishable from zero"* | L216, L303: *"facilitate re-engagement"* ([C6](#c6-diễn-giải-một-hệ-số-p--0978-thành-hiệu-ứng-có-hướng), [C7](#c7-cùng-lỗi-c6-lặp-lại-ở-mục-tổng-hợp-cơ-chế)) | +0.0001, **p = 0.978** |
| Hiệu ứng đệm tổng thể | *"do not support a uniform institutional-buffering effect"* | L119: *"reveal a coherent micro-mechanism"* ([C5](#c5-coherent-micro-mechanism-từ-ba-hệ-số-không-qua-được-fdr)) | **q = 0.228** cả ba điều khoản |

**Hai điểm cần sửa nếu tái sử dụng bản này:**

1. Abstract không nhắc **một chữ nào** về phát hiện mạnh nhất về lý thuyết của bài — sự phân kỳ hai biên ở Table 8 (depth **+2,84%** ở giá trị, **−0,17 pp** ở sống sót). Xem [F3](#f3-đặt-sự-phân-kỳ-hai-biên-làm-luận-điểm-trung-tâm). Câu cuối có gợi ý nhưng quá mờ và không có số.
2. *"directed pair–product fixed effects"* trong Abstract vs *"pair–HS2 fixed effects"* trong mục 4 — cùng một thứ, hai cách gọi. Chọn một. Đồng thời nói rõ FE là **directed** (i→j) trong khi clustering là **unordered pair** — không mâu thuẫn, nhưng phải nêu tường minh (liên quan [B6](#b6-clustering-được-mô-tả-khác-nhau-ở-4-chỗ)).
