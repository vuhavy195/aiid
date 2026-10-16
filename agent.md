# AIID PROJECT MASTER CONTEXT: DEEP TRADE AGREEMENTS, GEOPOLITICAL RISK, AND GLOBAL VALUE CHAIN RESILIENCE

> **Tài liệu tham chiếu toàn diện:** File này chứa toàn bộ bối cảnh học thuật, nguồn dữ liệu, quy chuẩn biến số, cấu trúc thư mục, kiến trúc pipeline (Python & R), chiến lược kinh tế lượng và hệ thống kết quả thực nghiệm của dự án AIID 2026. Mọi Agent làm việc với repository này chỉ cần đọc file này để nắm trọn vẹn ngữ cảnh dự án mà không cần rà soát lại từ đầu.

---

## 1. TỔNG QUAN VÀ BỐI CẢNH DỰ ÁN

- **Tên dự án:** Deep Trade Agreements (DTAs), Geopolitical Risk (GPR), and Intermediate-Goods Trade Resilience.
- **Tác giả / Hội thảo:** Vũ Hà Vy — Nghiên cứu kinh tế lượng phục vụ Hội thảo **AIID 2026**.
- **Câu hỏi nghiên cứu cốt lõi:**
  1. **Biên độ chuyên sâu (Intensive Margin):** Các Hiệp định Thương mại Sâu (Deep Trade Agreements - DTAs) đóng vai trò là "tấm đệm giảm sốc" (shock buffer) bảo vệ hay "khuếch đại độ nhạy cảm" (shock amplifier) đối với dòng chảy thương mại hàng hóa trung gian (intermediate goods) khi rủi ro địa chính trị toàn cầu (GPR) leo thang?
  2. **Dị biệt ngành (Sectoral Heterogeneity):** Mức độ chống chịu hoặc tổn thương phân hóa ra sao giữa 10 nhóm ngành kinh tế có cấu trúc chuỗi giá trị và độ đàn hồi thay thế khác nhau?
  3. **Cơ chế điều khoản chính sách (Mechanism Bundles & Individual Provisions):** Nhóm điều khoản nào (biên giới, môi trường, kỹ thuật số, đầu tư, dịch vụ) thúc đẩy hoặc cản trở khả năng chống chịu?
  4. **Biên độ mở rộng (Extensive Margin & Dynamics):**
     - *Tỷ lệ sống sót (Trade-Link Survival):* Rủi ro địa chính trị và chiều sâu DTA ảnh hưởng thế nào đến xác suất duy trì một liên kết thương mại đang tồn tại ($t-1 \to t$)?
     - *Phục hồi sau đứt gãy (Post-Exit Recovery):* Khi một liên kết thương mại bị đứt gãy, DTA có hỗ trợ tái gia nhập (re-entry) và khôi phục giá trị xuất khẩu (full recovery) trong 1–2 năm tiếp theo hay không?

---

## 2. NGUỒN DỮ LIỆU VÀ ĐỊNH NGHĨA BIẾN SỐ

| Hạng mục dữ liệu | Nguồn gốc | Mô tả chi tiết & Quy chuẩn |
| :--- | :--- | :--- |
| **Dữ liệu thương mại** | CEPII BACI HS2007 (V202601) | Dữ liệu thương mại song phương cấp độ HS 6-digit giai đoạn 2007–2023. |
| **Phân loại End-Use** | UN BEC Rev. 4 $\to$ HS2007 | Lọc các dòng thuế thuộc hàng hóa trung gian (*Intermediate goods* - BEC 111, 121, 21, 22, 31, 322, 42, 53). Hàng tiêu dùng (*Consumption goods*) dùng cho đối chứng DDD. |
| **Mẫu quốc gia** | 160 nền kinh tế cân bằng | 160 quốc gia/vùng lãnh thổ $\times$ 159 đối tác = 25,440 cặp song phương (directed pairs) $\times$ 17 năm (2007–2023) = 432,480 pair-years. |
| **Hiệp định DTA / RTA** | World Bank DTA Database & WTO RTA | - `fta_l1`: Biến nhị phân $=1$ nếu cặp quốc gia có hiệu lực hiệp định thương mại ưu đãi ở năm $t-1$.<br>- `depth_strict_l1_10`: Số lượng điều khoản có tính ràng buộc pháp lý (*legally enforceable*) ở năm $t-1$ chia cho 10 (thang đo: $0.0 \to 3.8$, tương ứng tối đa 38 điều khoản). |
| **Rủi ro Địa chính trị (GPR)** | Caldara & Iacoviello (2022) | Chuẩn hóa Z-score theo kỳ chuẩn lịch sử 1985–2019 ($Mean=0, SD=1$):<br>- `gpr_mean_z` ($GlobalGPR$): Giá trị trung bình năm của chỉ số GPR toàn cầu.<br>- `gpr_threat_z` ($GPRThreat$): Thành phần đe dọa địa chính trị.<br>- `gpr_act_z` ($GPRAct$): Thành phần hành động/sự kiện địa chính trị thực tế.<br>- `gpr_max_z` ($GPRPeak$): Mức đỉnh GPR tháng cao nhất trong năm.<br>- `PairGPRAvg` / `PairGPRMax`: Chỉ số GPR đặc thù song phương (bình quân hoặc max giữa nước xuất khẩu và nước nhập khẩu). |

---

## 3. CẤU TRÚC THƯ MỤC DỰ ÁN

```
H:\AIID_DTA_GPR\
├── agent.md                               # [FILE NÀY] Master Context & Project Knowledge Base
├── AIID2026_Abstract_VuHaVy.docx          # Bản thảo Abstract nộp hội thảo AIID 2026
├── data\
│   ├── raw\                               # Dữ liệu thô ban đầu
│   │   ├── baci_hs07_v202601\             # File CSV thương mại thường niên BACI 2007-2023
│   │   ├── bec\                           # Bảng tương quan HS2007 - BEC Rev.4
│   │   ├── dta_world_bank\                # DTA Horizontal Content v2 (.xlsx)
│   │   ├── geodist\                       # Khoảng cách địa lý CEPII GeoDist
│   │   ├── gpr\                           # Chuỗi thời gian GPR toàn cầu & quốc gia
│   │   └── wto_rta\                       # Dữ liệu WTO RTA
│   ├── interim\                           # Dữ liệu trung gian (DuckDB & Parquet)
│   │   ├── hs07_bec4_clean_map.csv        # Bảng mapping HS2007 - BEC4 đã làm sạch
│   │   ├── dta_active_agreement_records_160.parquet
│   │   ├── dta_active_pair_year_le_provisions_160.parquet
│   │   ├── trade_positive_pair_hs2_year_intermediate.parquet
│   │   └── country_specific_pair_gpr_2007_2023.parquet
│   └── processed\                         # Panel ước lượng chính thức (Định dạng Parquet tối ưu)
│       ├── country_sample_160.csv         # Danh sách 160 quốc gia nghiên cứu
│       ├── dta_pair_year_core_160.parquet # Panel hiệp định cấp độ cặp-năm
│       ├── estimation_hs2_ppml_compact.parquet        # Master panel PPML cấp HS2 (16.75M dòng)
│       ├── estimation_hs2_ppml_mechanisms.parquet     # Panel cơ chế 5 bundles & 14 điều khoản
│       ├── estimation_hs2_trade_link_survival.parquet # Panel phân tích tỷ lệ sống sót LPM (8.22M dòng)
│       ├── estimation_hs2_post_exit_recovery.parquet  # Panel phân tích hồi phục sau đứt gãy (1.24M sự kiện)
│       ├── estimation_hs2_ppml_country_gpr.parquet    # Panel kiểm định với country-specific GPR
│       ├── estimation_hs2_survival_country_gpr.parquet# Panel survival với country-specific GPR
│       └── estimation_pair_enduse_year_ddd.parquet    # Panel Triple-Diff hàng trung gian vs tiêu dùng
├── python\                                # 17 Python scripts xử lý dữ liệu và tạo panel (Step 01 -> 15b)
├── r\                                     # 16 R scripts ước lượng kinh tế lượng PPML/LPM (Step 09 -> 16)
├── outputs\
│   ├── audit\                             # 100+ báo cáo kiểm toán số liệu (step*_report.txt, *.csv)
│   ├── tables\                            # Bảng hệ số ước lượng trích xuất trực tiếp từ mô hình R
│   ├── figures\                           # Biểu đồ mô hình pilot
│   ├── models\                            # File RDS lưu mô hình pilot (Step 9/9b)
│   └── paper_outputs\                     # KẾT XUẤT CHÍNH THỨC CHO BÀI BÁO:
│       ├── main_tables\                   # Tables 1 đến 8 (CSV)
│       ├── appendix_tables\               # Appendix Tables A1 đến A4 (CSV)
│       ├── figures\                       # Figures 1 đến 4 & Appendix Figures (PDF & PNG 300dpi)
│       ├── figure_data\                   # Dữ liệu vẽ đồ thị (CSV)
│       ├── AIID_DTA_GPR_Paper_Tables.xlsx # Master Excel Workbook chứa toàn bộ bảng biểu
│       ├── paper_output_manifest.csv      # Danh mục kiểm kê output
│       └── paper_output_report.txt        # Báo cáo tổng kết hoàn thành sinh output
```

---

## 4. CHI TIẾT PIPELINE XỬ LÝ DỮ LIỆU VÀ KINH TẾ LƯỢNG

### A. Pipeline Tiền xử lý dữ liệu (Python)
- **`01_inventory_raw.py`:** Kiểm kê toàn bộ file dữ liệu thô đầu vào.
- **`02_audit_reference_files.py` / `02b_corrected_dta_audit.py`:** Rà soát và chuẩn hóa dữ liệu DTA Ngân hàng Thế giới, xử lý mã định danh.
- **`03_audit_baci_and_build_country_sample.py`:** Lọc mẫu 160 quốc gia cân bằng có báo cáo thương mại ổn định suốt 2007–2023.
- **`04_finalize_sample_and_bec_map.py`:** Làm sạch bảng phân loại hàng hóa trung gian HS2007–BEC Rev.4 (`hs07_bec4_clean_map.csv`).
- **`05_build_positive_trade_aggregates.py`:** Tổng hợp kim ngạch thương mại dương theo cấp độ cặp-năm và cặp-HS2-năm (`trade_positive_pair_hs2_year_intermediate.parquet`).
- **`06_build_dta_pair_year_panel.py`:** Ghép dữ liệu DTA & WTO cho $160 \times 159 = 25,440$ cặp song phương qua 17 năm ($432,480$ dòng).
- **`07_build_annual_gpr_variables.py`:** Chuẩn hóa các biến GPR toàn cầu và GPR cấp quốc gia theo thang đo Z-score lịch sử 1985–2019.
- **`08_build_estimation_panels.py`:** Tạo các master panel phục vụ ước lượng kinh tế lượng.
- **`10a_build_compact_hs2_ppml_data_FIXED.py`:** Tối ưu hóa panel HS2 rút gọn (16,752,461 dòng; 985,562 nhóm pair-HS2; 47.52% zero trade).
- **`12a_build_hs2_mechanism_panel.py`:** Tạo panel tích hợp 5 nhóm điều khoản DTA (bundles) và 14 điều khoản có ràng buộc pháp lý.
- **`13a_build_hs2_trade_link_survival_FIXED.py`:** Xây dựng panel biên độ mở rộng theo dõi sự sống sót của các liên kết thương mại đang tồn tại (8,219,579 quan sát link-year có nguy cơ đứt gãy).
- **`14a_build_post_exit_recovery_panel.py`:** Xây dựng panel theo dõi 1,237,520 sự kiện đứt gãy liên kết để đo lường xác suất tái gia nhập và phục hồi kim ngạch.
- **`15b_build_country_specific_pair_gpr_panels_FIXED.py`:** Tạo panel với các cú sốc rủi ro địa chính trị song phương cụ thể cho từng cặp quốc gia.

### B. Pipeline Kinh tế lượng & Kết xuất Bài báo (R)
- **`09_r_pilot_ppml.R` & `09b_pilot_diagnostics.R`:** Ước lượng mô hình pilot PPML và mô hình ba lần vi phân DDD (Intermediate vs. Consumption) nhằm xác thực chiến lược nhận dạng.
- **`10b_full_hs2_core_ppml_FIXED.R`:** Mô hình trọng lực PPML chuẩn (`fixest::fepois`) trên 16.75 triệu dòng với 4 chiều Fixed Effects: Cặp-HS2 FE, Nước xuất khẩu-Năm FE, Nước nhập khẩu-Năm FE, Mã HS2-Năm FE.
- **`10c_full_hs2_robustness_ppml.R`:** Kiểm định độ bền baseline (Joint FTA + Depth, các thành phần GPR Threat, Act, Peak, loại trừ năm chiến sự 2022).
- **`11_hs2_sector_heterogeneity_ppml.R`:** Phân tích dị biệt trên 10 phân ngành HS2, kiểm soát đa kiểm định giả định thống kê bằng Benjamini-Hochberg False Discovery Rate (BH-FDR).
- **`12b_dta_mechanism_bundle_ppml.R` & `12c_individual_dta_provision_screen.R`:** Ước lượng tác động của 5 nhóm chính sách DTA và sàng lọc 14 điều khoản riêng lẻ.
- **`13b_hs2_trade_link_survival_lpm.R` & `13c_trade_link_survival_robustness_FIXED.R`:** Mô hình Linear Probability Model (LPM) ước lượng xác suất duy trì liên kết thương mại, kiểm soát quy mô trễ và kiểm định Jackknife leave-one-year-out (16 vòng).
- **`14b_post_exit_recovery_lpm_FIXED.R`:** Mô hình LPM ước lượng tốc độ tái gia nhập và khôi phục giá trị trong 1 năm và 2 năm sau đứt gãy.
- **`15a_fta_only_depth_robustness.R` & `15c_country_specific_pair_gpr_robustness_FIXED.R`:** Ước lượng độ sâu DTA trong tập con các nước đã có FTA và kiểm định với cú sốc GPR song phương.
- **`16_build_paper_tables_figures_FIXED.R`:** Tổng hợp tất cả bảng biểu chính, bảng phụ lục, xuất file Excel `AIID_DTA_GPR_Paper_Tables.xlsx`, biểu đồ PDF/PNG 300dpi và manifest.

---

## 5. TỔNG HỢP KẾT QUẢ THỰC NGHIỆM CHÍNH (EMPIRICAL FINDINGS)

### Table 3: Baseline PPML — Intensive Margin ($N = 16,752,356$)
*Mô hình:* PPML trọng lực cấp độ HS2, kiểm soát Pair-HS2 FE, Exporter-Year FE, Importer-Year FE, HS2-Year FE. Sai số chuẩn phân cụm đa chiều: Pair + Year multiway clustering.
- **Mô hình (1) FTA Interaction:** $\beta_{GPR \times FTA} = -0.0241^{**}$ ($SE = 0.0107, p = 0.024$).
  $\to$ **Tác động:** Khi GPR toàn cầu tăng 1 độ lệch chuẩn lịch sử (1 SD), thương mại hàng trung gian giữa các đối tác có FTA **giảm -2.38%** so với đối tác không có FTA.
- **Mô hình (2) Depth Interaction:** $\beta_{GPR \times Depth} = -0.0053$ ($SE = 0.0047, p = 0.255$).
  $\to$ **Tác động:** Hiệu ứng của chiều sâu DTA không có ý nghĩa thống kê ở mức tổng thể.
- **Mô hình (3) Joint FTA + Depth:** $\beta_{GPR \times FTA} = -0.0382^{**}$ ($SE = 0.0171, p = 0.025$, tác động $-3.75\%$), trong khi $\beta_{GPR \times Depth} = +0.0099$ ($SE = 0.0078, p = 0.202$, tác động $+0.99\%$).
- **Ý nghĩa:** Việc tham gia FTA làm tăng mức độ phơi nhiễm trước rủi ro địa chính trị do mức độ tích hợp chuỗi cung ứng sâu hơn, nhưng các cam kết thể chế sâu (DTA depth) có xu hướng bù đắp/giảm nhẹ bớt sự nhạy cảm này.

---

### Table 4 & Figure 3: Dị biệt theo ngành hàng (Sector Heterogeneity)
*Phân tích 10 phân ngành HS2, xếp theo mức độ tổn thương khi GPR tăng 1 SD (vượt qua kiểm định đa giả thuyết BH-FDR $p < 0.10$):*
1. **Thiết bị vận tải (Transport equipment - HS 86-89):**
   - $GPR \times FTA: \beta = -0.0474^{**}$ (Giảm **-4.63%**, BH-FDR $p = 0.026$)
   - $GPR \times Depth: \beta = -0.0184^{*}$ (Giảm **-1.83%**, BH-FDR $p = 0.062$)
2. **Dệt may và da giày (Textiles & footwear - HS 50-67):**
   - $GPR \times FTA: \beta = -0.0447^{***}$ (Giảm **-4.37%**, BH-FDR $p = 0.003$)
   - $GPR \times Depth: \beta = -0.0201^{***}$ (Giảm **-1.99%**, BH-FDR $p = 0.005$)
3. **Máy móc và thiết bị điện tử (Machinery & electronics - HS 84-85):**
   - $GPR \times FTA: \beta = -0.0349^{**}$ (Giảm **-3.43%**, BH-FDR $p = 0.026$)
   - $GPR \times Depth: \beta = -0.0135^{*}$ (Giảm **-1.34%**, BH-FDR $p = 0.077$)
4. **Chế tạo chính xác & công nghiệp khác (Precision & other manufactures - HS 90-99):**
   - $GPR \times FTA: \beta = -0.0320^{**}$ (Giảm **-3.15%**, BH-FDR $p = 0.026$)
   - $GPR \times Depth: \beta = -0.0173^{***}$ (Giảm **-1.72%**, BH-FDR $p = 0.006$)
5. **Nhựa, cao su và da (Plastics, rubber & leather - HS 39-43):**
   - $GPR \times FTA: \beta = -0.0194^{**}$ (Giảm **-1.92%**, BH-FDR $p = 0.026$)
   - $GPR \times Depth: \beta = -0.0108^{*}$ (Giảm **-1.07%**, BH-FDR $p = 0.062$)
- **Nhận định:** Các ngành có chuỗi cung ứng phức tạp, chuyên môn hóa sâu và tính chuyên biệt của tài sản cao (ô tô, điện tử, dệt may) chịu tổn thương nặng nề nhất khi rủi ro địa chính trị gia tăng.

---

### Table 5, Table 6 & Figure 4: Biên độ mở rộng — Tỷ lệ sống sót liên kết thương mại ($N = 8,045,131$)
*Mô hình:* LPM ước lượng xác suất duy trì liên kết thương mại dương ở $t$ khi $t-1 > 0$, kiểm soát quy mô thương mại trễ (`LaggedTrade`) và 4 chiều FE.
- **Mô hình Joint có kiểm soát quy mô:**
  - $GPR \times FTA: \beta = +0.0028^{*}$ ($SE = 0.0015, p = 0.086$, tăng $+0.28$ điểm phần trăm).
  - $GPR \times DTA Depth: \beta = -0.0052^{***}$ ($SE = 0.0017, p = 0.007$, **giảm -0.52 điểm phần trăm** xác suất sống sót cho mỗi 10 điều khoản ràng buộc).
- **Kiểm định Jackknife Leave-One-Year-Out (Figure 4):**
  - Hệ số $GPR \times Depth$ luôn âm nghiêm ngặt trong khoảng $[-0.0068, -0.0040]$ và có ý nghĩa thống kê ($p < 0.01$) trong toàn bộ 16 vòng loại trừ từng năm, chứng minh tính bền vững tuyệt đối của kết quả.

---

### Table 7 & Phụ lục A4: Phục hồi sau đứt gãy (Post-Exit Recovery Dynamics)
*Mô hình:* LPM trên 1,151,310 sự kiện đứt gãy liên kết (directed-pair FE):
- **Tái gia nhập trong 1 năm ($Reentry1Y$):**
  - $GPR \times Depth: \beta = -0.0035^{**}$ ($p = 0.044$, giảm $-0.35$ pp).
- **Tái gia nhập trong 2 năm ($Reentry2Y$):**
  - $GPR \times Depth: \beta = +0.0001$ ($p = 0.978$, hiệu ứng trung tính).
- **Khôi phục hoàn toàn kim ngạch trong 1-2 năm ($FullRecovery$):**
  - Hệ số không có ý nghĩa thống kê ($p > 0.40$).
- **Ý nghĩa:** DTAs không thể ngăn chặn sự đình trệ ngắn hạn (1 năm) sau khi liên kết bị đứt gãy dưới tác động của rủi ro địa chính trị, nhưng không cản trở sự hồi phục trong trung hạn (2 năm).

---

### Table 8 & Phụ lục A2, A3: Cú sốc GPR quốc gia & Cơ chế điều khoản
- **Cú sốc Country-Specific Pair GPR (Table 8):**
  - Khi đo lường rủi ro bằng trung bình GPR của cặp xuất nhập khẩu ($PairGPRAvg$): $GPR \times FTA = -0.0852^{***}$ (giảm $-8.17\%$), $GPR \times Depth = +0.0280^{**}$ (tăng $+2.84\%$).
- **Cơ chế điều khoản DTA bảo vệ (Appendix Table A3):**
  - **Môi trường (Environmental laws):** $\beta = +0.0384^{**}$ (Hiệu ứng $+3.91\%$, $p = 0.049$)
  - **Nghiên cứu & Công nghệ (Research & technology):** $\beta = +0.0343^{**}$ (Hiệu ứng $+3.49\%$, $p = 0.041$)
  - **Chính sách cạnh tranh (Competition policy):** $\beta = +0.0353^{**}$ (Hiệu ứng $+3.60\%$, $p = 0.037$)
  - **Ý nghĩa:** Các điều khoản thúc đẩy đổi mới công nghệ, sân chơi bình đẳng và chuẩn mực môi trường giúp doanh nghiệp xây dựng chuỗi cung ứng linh hoạt và bền vững hơn trước các cú sốc địa chính trị.

---

## 6. QUY TẮC BẮT BUỘC KHI VẬN HÀNH DỰ ÁN

Để đảm bảo tính toàn vẹn dữ liệu và đồng bộ với User, mọi Agent khi tương tác với workspace này **BẮT BUỘC** tuân thủ 3 nguyên tắc:

1. **Tuyệt đối không tự ý tạo hoặc sửa file** (Python, R, Markdown, Data...) trong workspace `H:\AIID_DTA_GPR` (hoặc các ổ đĩa máy tính / Google Drive) nếu chưa có yêu cầu và sự cho phép rõ ràng từ User.
2. **Không chạy lại các mô hình kinh tế lượng nặng** trừ khi User yêu cầu rõ ràng. Tất cả kết quả mô hình đã được tính toán, kiểm định và lưu trữ hoàn chỉnh tại `outputs/paper_outputs/` và `outputs/tables/`.
3. **Mọi script thử nghiệm/phân tích phụ** (nếu cần thiết) phải được lưu và thực thi tại thư mục tạm thời `scratch/` của conversation, không được ghi đè hay sinh file rác vào thư mục gốc của dự án.
