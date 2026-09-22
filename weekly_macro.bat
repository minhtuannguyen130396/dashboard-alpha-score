@echo off
REM ===========================================================================
REM  Nhip HANG TUAN cua tang vi mo & nganh.
REM
REM  Vi sao phai co file nay thay vi "nho chay tay": hai thu trong tang nay
REM  DONG BANG THEO NGAY va khong dung lai duoc.
REM
REM    * BCTC nganh + chuoi vi mo -- FireAnt chi tra trang thai HOM NAY, nen
REM      ngay khong chay la ngay mat vinh vien.
REM    * Diem tin do Gemini cham -- gia thuyet H3 ("diem tin co them gi ngoai
REM      cac cot do duoc") KHONG backfill duoc: mot model cham tin thang 3 vao
REM      hom nay da biet thi truong di dau sau do. Chi tich luy tien duoc, va
REM      no chi tich luy neu co cai gi chay deu.
REM    * Dinh gia dung san cua FireAnt (`/estimated-price`) -- cung mot loai:
REM      endpoint chi tra trang thai HOM NAY, khong co endpoint nao tra lai
REM      dinh gia cua thang truoc. Buoc 6 ben duoi.
REM
REM  Dang ky chay tu dong (chay 1 lan, trong cua so Admin):
REM
REM    schtasks /create /tn "vn-ta macro weekly" /tr "D:\Trader\dashboard-alpha-score\weekly_macro.bat" /sc weekly /d SUN /st 07:00
REM
REM  Xem lich da dang ky:   schtasks /query /tn "vn-ta macro weekly"
REM  Bo lich:               schtasks /delete /tn "vn-ta macro weekly" /f
REM
REM  Can GEMINI_API_KEY (hoac GOOGLE_API_KEY) trong bien moi truong HE THONG --
REM  bien cua rieng phien terminal khong den duoc Task Scheduler.
REM ===========================================================================

setlocal
cd /d "%~dp0"

set LOGDIR=%~dp0macro\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f "tokens=1-3 delims=/-. " %%a in ("%DATE%") do set STAMP=%%c%%b%%a
set LOG=%LOGDIR%\weekly_%STAMP%.log

echo ================================================== >> "%LOG%"
echo [%DATE% %TIME%] bat dau >> "%LOG%"

REM --- 1. Chi so nganh + RRG + thanh vien (khong dong bang, chay lai duoc) ---
python -m src.macro.icb --levels 1,2        >> "%LOG%" 2>&1
python -m src.macro.rrg                     >> "%LOG%" 2>&1
python -m src.macro.members                 >> "%LOG%" 2>&1

REM --- 2. DONG BANG theo ngay -- phan khong chay lai duoc ---
python -m src.macro.fundamentals            >> "%LOG%" 2>&1
python -m src.macro.series                  >> "%LOG%" 2>&1

REM --- 3. Tin nhom. 12 trang la du cho nhip tuan; chi can bat bai moi.
REM     Cao sau (--pages 180) chi lam mot lan luc dung kho.
python -m src.macro.feed --pages 20         >> "%LOG%" 2>&1

REM --- 4. Cham tin bang Gemini -- TICH LUY cho H3 ---
python -m src.macro.gemini                  >> "%LOG%" 2>&1

REM --- 5. Hieu chuan lai. Tran diem trong score.py la he qua cua buoc nay.
python -m src.macro.calibrate               >> "%LOG%" 2>&1

REM --- 6. DONG BANG dinh gia dung san (tang ban phan tich, GD0).
REM     Chua co gi doc toi kho nay -- va do chinh la ly do phai chay tu bay gio:
REM     toi luc tang dinh gia can den no thi da muon may thang.
python -m src.desk.freeze                   >> "%LOG%" 2>&1

REM --- 7. Hieu chuan lai dong tien (D1/D2). Khac buoc 6: cai nay chay lai duoc
REM     bat cu luc nao vi du lieu da nam tren dia -- chay hang tuan chi de ket
REM     luan khong mac ket o mau cua nam ngoai.
python -m src.desk.calibrate_flows          >> "%LOG%" 2>&1

REM --- 8. BCTC quy (40 ky moi ma, 2 request). Cao lai duoc, nhung mua BCTC ra
REM     theo dot nen chay hang tuan la du bat kip.
python -m src.desk.financials               >> "%LOG%" 2>&1

REM --- 9. Bao cao phan tich cua cac CTCK. Cua so 30 ngay la du cho nhip tuan;
REM     cao sau (120 ngay) chi lam mot lan luc dung kho.
python -m src.desk.consensus 30             >> "%LOG%" 2>&1

REM --- 10. Hieu chuan lai dai dinh gia (V1/V2) sau khi BCTC da moi.
python -m src.desk.calibrate_valuation      >> "%LOG%" 2>&1

echo [%DATE% %TIME%] xong >> "%LOG%"
endlocal
