# Đánh giá recommender bằng persona

20 persona × 5 cấu hình trọng số, top-10.
Trung bình trên các persona có kết quả. 'persona_du_n' = số persona nhận đủ 10 kết quả.

| config               | persona_du_n   |   giá/ngân sách |   % giá hời |   % ở ghép |   km TB |   tiện nghi TB |   m² TB |   % ước lượng m² |   số quận |   số nguồn |
|:---------------------|:---------------|----------------:|------------:|-----------:|--------:|---------------:|--------:|-----------------:|----------:|-----------:|
| baseline: rẻ nhất    | 20/20          |            0.89 |        0.18 |          0 |    3.71 |           2.86 |   25.9  |             0.52 |      4.05 |       3.15 |
| mặc định 30/25/25/20 | 20/20          |            0.81 |        0.67 |          0 |    2.63 |           4.61 |   28.07 |             0.13 |      3.5  |       3.7  |
| nghiêng giá trị      | 20/20          |            0.72 |        0.92 |          0 |    2.76 |           4.26 |   29.84 |             0.11 |      3.65 |       3.75 |
| nghiêng khoảng cách  | 20/20          |            0.78 |        0.61 |          0 |    2.28 |           3.86 |   26.36 |             0.22 |      2.95 |       3.45 |
| đều 25 mỗi mục       | 20/20          |            0.81 |        0.66 |          0 |    2.67 |           4.74 |   28.14 |             0.14 |      3.45 |       3.7  |

Persona không đủ 10 kết quả: không có

The persona table above is synthetic (behavioural measures), not user feedback.

## Real user feedback (👍/👎 collected in the app)

```
{
 "labels": 16,
 "sessions": 2,
 "share_up": 0.75,
 "hand": {
  "ndcg@10": 1.0,
  "p@5": 0.725
 },
 "cheapest_first": {
  "ndcg@10": 0.981,
  "p@5": 0.725
 },
 "random": {
  "ndcg@10": 0.945,
  "p@5": 0.725
 },
 "learned_cv": {
  "ndcg@10": 0.971,
  "p@5": 0.725
 },
 "learned_weights": {
  "price": 0.0,
  "value": 0.379,
  "distance": 0.0,
  "amenity": 0.621,
  "q_not_sublet": 0.0,
  "q_has_address": 0.0,
  "q_district_ok": 0.0
 }
}
```
