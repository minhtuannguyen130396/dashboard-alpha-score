# _mk_record()

> God node · 22 connections · `tests\test_smart_money.py`

## What It Is

Factory function tạo synthetic `StockRecord` dùng trong test suite Smart Money. Là god node vì **mọi test case đều gọi nó** — không phải vì nó có logic phức tạp, mà vì nó là điểm tập trung dữ liệu test.

Cho phép test setup linh hoạt: tạo records với các giá trị prop flow, foreign flow, volume, giá tuỳ chỉnh để kiểm tra các edge cases (no data → zero confidence, opposing signals cancel, persistence pattern, toxic flow detection...). Xem [[Smart Money Tests]] cho danh sách đầy đủ các test cases.

## Connections by Relation

### calls
- [[.test_strong_accumulation_positive_value()]] `EXTRACTED`
- [[.test_no_prop_data_zero_confidence()]] `EXTRACTED`
- [[.test_distribution_negative_value()]] `EXTRACTED`
- [[.test_single_huge_print_does_not_dominate()]] `EXTRACTED`
- [[.test_buy_dominates()]] `EXTRACTED`
- [[.test_no_foreign_activity_zero_confidence()]] `EXTRACTED`
- [[.test_trigger_zero_when_phase2_disabled()]] `EXTRACTED`
- [[.test_primitive_bucket_matches_class_attribute()]] `EXTRACTED`
- [[.test_opposite_signs_cancel()]] `EXTRACTED`
- [[.test_label_classification()]] `EXTRACTED`
- [[.test_concentration_load_up_day()]] `EXTRACTED`
- [[.test_concentration_no_signal_low_rvol()]] `EXTRACTED`
- [[.test_persistence_high_when_consistent()]] `EXTRACTED`
- [[.test_persistence_low_when_noisy()]] `EXTRACTED`
- [[.test_persistence_multiplier_lowers_setup_confidence()]] `EXTRACTED`
- [[.test_toxic_flow_detection()]] `EXTRACTED`
- [[.test_toxic_flow_not_triggered_normal()]] `EXTRACTED`
- [[.test_toxic_label_overrides()]] `EXTRACTED`
- [[.test_phase2_disabled_matches_phase1_setup()]] `EXTRACTED`
- [[.test_v5_runs_end_to_end()]] `EXTRACTED`

### contains
- [[test_smart_money.py]] `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*