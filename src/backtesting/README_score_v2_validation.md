# Score V2 Validation Checklist

## Muc tieu

Tai lieu nay dung de kiem tra `score v2` sau khi implement.

## A/B test bat buoc

So sanh:
- `v1`
- `v2`

Tren cung:
- tap ma
- khoang ngay
- quy tac vao lenh/thoat lenh

## Chi so can bao cao

- so lenh
- ty le thang
- profit factor
- expectancy
- avg hold days
- avg gain
- avg loss
- max drawdown
- tong loi nhuan

## Kiem tra theo nhom co phieu

- VN30
- Large Cap
- Mid Cap
- Other

## Kiem tra theo regime

- uptrend manh
- downtrend manh
- sideway
- volatility cao
- volatility thap

## Kiem tra logic score

1. Mot ngay khong du du lieu:
- khong duoc phat sinh buy/sell sai

2. Co mo hinh nen dep nhung volume yeu:
- score phai bi giam

3. Co breakout ro nhung candle pattern trung tinh:
- score van co the duoc kich hoat nho confirmation + volume + trend

4. Sideway ADX thap:
- score phai han che overtrade

5. Gia sat resistance:
- can co blocker hoac tru diem structure

## Dieu kien dat

- Khong duoc tang trade count bang moi gia trong khi expectancy xau di.
- Uu tien:
  - expectancy tang
  - max drawdown giam
  - profit factor tang
- Neu win rate giam nhe nhung expectancy tang thi van chap nhan duoc.

