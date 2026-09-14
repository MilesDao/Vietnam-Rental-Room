# Cleaning report

Run at: 2026-09-10T08:30:02.261065+00:00
Source: `data/interim/parsed_*.parquet` (Tier 1 only -- mogi.vn)

## Row counts

- Raw (post-ingest dedupe on listing_id): 2339
- Dropped, price unparseable/negotiable: 30
- Dropped, area unparseable: 1
- After missing-value drop: 2308
- Duplicate clusters found: 1876 (288 with >1 member, largest = 14)
- Near-exact text matches (Jaccard >= 0.85): 86
- Attribute matches (location+area+price): 346
- **Final row count: 1876**

## Missing values (pre-clean, raw corpus)

| column | nulls |
|---|---|
| price_vnd_month | 30 |
| area_m2 | 1 |
| lat | 90 |
| lon | 90 |
| geo_confidence | 90 |
| poster_name | 1933 |
| poster_id_hash | 1933 |

## Outliers (flagged, not dropped)

Total flagged: 23

| reason | count |
|---|---|
| price_per_m2_district_outlier | 17 |
| area_too_small | 8 |
| price_too_high | 3 |
| area_too_large | 2 |

## Amenity extraction hit rates

Keyword lexicon in `src/clean/amenities.py`; NOT manually validated for
precision/recall on a sample yet (PLAN.md Phase 3 checklist item -- backlog).

| amenity | share of listings |
|---|---|
| khep_kin | 35.0% |
| gio_giac_tu_do | 1.2% |
| gac_xep | 9.6% |
| ban_cong | 27.7% |
| may_giat | 56.2% |
| thang_may | 33.6% |
| khong_chung_chu | 36.1% |
| chung_chu | 4.8% |
| dieu_hoa | 72.1% |
| nong_lanh | 57.5% |
| tu_lanh | 41.2% |
| cho_de_xe | 18.9% |
| an_ninh | 50.4% |
| noi_that_day_du | 24.9% |
| cua_so | 37.3% |
| gan_truong_hoc | 7.3% |

## Sample duplicate clusters (largest 5, for a manual spot-check)

- cluster `mogi_21403102` (14 listings):
  - phòng trọ mới xây full đồ siêu siêu đẹp, đường xá tiện lợi
  - CCMN Ful nội thất tại Yên Xá,Thanh Trì,Hà Nội
  - Cho thuê CCMN chính chủ tại Yên Xá đầy đủ đồ
  - Chung cư mini khu vực Yên Xá- Full đồ
  - Tôi còn 2 phòng trống 26m2 cho thuê, nhà mới, full nội thất khu Yên Xá
  - Cho thuê phòng trọ 26 m2 Yên Xá, Tân Triều giá rẻ 3,5tr/th, Full đồ.
  - CCMN mới xây - 87 Yên Xá - Đầy đủ đồ
  - Phòng trọ, CCMN full đồ, ban công 21 Yên Xá, Tân Triều
  - Cho thuê chung cư mini mới tinh full đồ ngõ 39 Yên Xá
  - Chung cư mini khu vực Yên Xá ( Phòng full đồ - khép kín)
  - Chung cư mini khu vực Yên Xá- Tân Triều
  - Chung cư mini khu vực Yên Xá - Tân Triều
  - Chung cư mini khu vực Yên Xá Tân Triều
  - Mời thuê phòng Số 17 ngõ 39 Yên Xá
- cluster `mogi_21939455` (11 listings):
  - CCMN 25m2 - đầy đủ nội thất - Yên Xá, Thanh Trì - chính chủ
  - Phòng trọ 25m2, mới xây , không chung chủ, ngõ 87 Yên Xá
  - Cho thuê phòng trọ, căn hộ dịch vụ khu vực Yên Xá
  - Phòng trọ mới xây, full đồ, siêu đẹp tại 39 Yên Xá
  - Cho thuê CCMN full đồ tại Yên Xá, Tân Triều
  - CCMN Ngõ 87 Yên Xá gác xép full đồ
  - Chính chủ cho thuê phòng chung cư mini - full đồ - có thang máy
  - Chung cư mini khu vực Yên Xá full đồ đầu tháng 4 vào ở
  - CCMN YÊN XÁ 20-25m2 có gác xép, ban công thoáng mát
  - Cho thuê chung cư mini 2 Ngủ mới tinh ngõ 39 Yên Xá
  - Chung cư mini khu vực Yên Xá - Tân Triều
- cluster `mogi_22667351` (10 listings):
  - Ký túc xá cao cấp, tiện nghi đi bộ 5 phút đến ĐH Y Dược, BV Chợ Rẫy
  - KTX gần BV Chợ Rẫy, ĐH Y Dược, an toàn cao về phòng cháy chữa cháy.
  - Cho thuê phòng riêng cách BV Chợ Rẫy, ĐH Y Dược 5 phút đi bộ
  - KÝ TÚC XÁ sát ĐH Y Dược, chi phí TRỌN GÓI, full nội thất RẺ-ĐẸP,
  - KTX UY TÍN - CHẤT LƯỢNG, đi bộ 5 phút đến BV Chợ Rẫy, ĐH Y Dược, HV...
  - KÝ TÚC XÁ dành cho BS, nhân viên y tế BV CHỢ RẪY, ĐH Y DƯỢC
  - Ký túc xá tiện nghi đi bộ 5 phút đến ĐH Y Dược, BV Chợ Rẫy
  - Ký túc xá tiện nghi đi bộ 5 phút đến ĐH Y Dược, BV Chợ Rẫy
  - KTX an toàn cao về phòng cháy chữa cháy., 5 phút đi bộ đến BV Chợ Rẫy,
  - Ký túc xá cao cấp, hiện đại và tiện nghi đi bộ 5 phút đến ĐH Y Dược, B
- cluster `mogi_21359198` (6 listings):
  - CCMN - 80 Bà Triệu - Chính chủ đầy đủ đồ
  - CCMN - Chính chủ - 80 Bà Triệu - Hà Đông đầy đủ đồ
  - Phòng trong CC mini full nội thất tại Bà Triệu, Tô Hiệu, Hà Đông
  - CCMN đường Bà Triệu, gần chợ Hà Đông full đồ, ban công thoáng
  - CCMN full đồ mới xây 80 Bà Triệu, Hà Đông
  - Cho thuê phòng trọ KV Bà Triệu Hà Đông full đồ
- cluster `mogi_21599127` (6 listings):
  - CHo thuê căn studio full đồ thoáng mát, nhà mới ở Trần Thái Tông
  - Phòng 30m2 full đồ bếp ngủ tách riêng ở Trần Thái Tông
  - Phòng đẹp full đồ nhà mới xây, thang máy, khóa vân tay
  - [CẦU GIẤY] Cho Thuê CCMN 1 BẾP 1 NGỦ ĐẦY ĐỦ TIỆN NGHI, Có Ban Công
  - chung cư mini 30m2 khép kín full đồ ở Trần Thái Tông
  - Cho thuê phòng mới ban công full đồ Trần Thái Tông

## Known gaps (not built in this pass)

- **Admin-unit crosswalk (Vietnam's 2025 63->34 province reorg, district
  level dissolved)**: not built. `district`/`province` carry the legacy
  labels as scraped, normalized only for whitespace/unicode -- no
  `admin_code` column yet. Needs an authoritative crosswalk sourced into
  `data/external/` before Phase 4 spatial joins should trust anything
  beyond the raw legacy label.
- **Image-hash (pHash/dHash) dedup layer**: not run. The corpus stores
  `image_urls`, not downloaded image bytes, so there's nothing to hash yet.
- **Tier-2 cross-post dedup + Tier1<->Tier2 overlap report**: not
  applicable -- no Tier-2 (social) source has been crawled.
- **Manual precision/recall validation** of the dedupe clusters and the
  amenity lexicon (both called for explicitly in PLAN.md Phase 3): not
  done by a human yet -- see the sample clusters above as a starting point.
