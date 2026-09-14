# 道路驅動農村：灰模預覽

本頁描述可獨立重建的灰模版本。構圖已確認，後續接入的住宅、農田與電桿見 [資產場景](rural_scene.md)。

以 `docs/rural_reference_layout.json` 為來源，輸出 10 條道路 Curve、6 個用途分區（住宅 1、田地 4、保留區 1）、49 戶住宅及 33 塊田地灰模。住宅包含 49 個主屋與 33 個側屋，共 82 個建築量體。這是構圖檢查階段，尚未接入農田或建築資產。

第二版將主要彎道移至聚落西側與南側，新增南側巷道，延伸中間、東側及西側巷道。所有道路透過端點或線段交會連到同一個路網；住宅由第一版的 17 棟增加為 49 棟，分布到南側與內部支路。面寬和進深依種子變化，窄巷優先分配建築，再配置主路住宅。完整 footprint 必須避開所有道路並位於住宅區內，不能只檢查四個角落或所屬道路。

第三版將原本的建築盒視為可用基地範圍，在其中配置後方主屋、前院及較低的側屋。33 戶形成 L 形量體，其餘 16 戶為主屋加前院。側屋可在左側或右側；主屋依類型有不同高度。各戶保留 2 m 寬的步行入口，從道路邊緣經退縮地帶、院落接至主屋前牆。側屋不占用入口，也不會超出原本基地。院落由基地內留出，因此總建築覆蓋面積會比第二版整塊建築盒小。

```sh
blender -b --factory-startup --python-exit-code 1 --python scripts/build_rural_blockout.py -- --render
```

輸出：

- `dist/TCity_Rural_Blockout.blend`：可編輯場景，預設空拍相機，另有正上方與住宅近景相機。
- `renders/rural_blockout_aerial.png`：空拍構圖。
- `renders/rural_blockout_plan.png`：正上方配置。
- `renders/rural_blockout_housing.png`：院落、側屋及入口通道近景。

以 `--layout <JSON 路徑>` 指定另一份配置。所有座標以公尺處理，未描摹真實地籍。

在 Blender 的 `TCity • Rural composition` 集合中，`Road inputs` 保留折線 Curve；編輯控制點會透過 Geometry Nodes 同步更新平坦路面。`Zone inputs` 保留各用途的單面多邊形，`Building placeholders` 保留住宅所屬道路、分區、類型、朝向及入口資料，主屋／側屋透過 `building_part` 區分，並共用同一戶的 `source_id`。`Yards and access` 包含前院、院內通道與道路接入平面，`entry`、`door`、`road_entry` 記錄院門、主屋入口與道路邊緣位置。`Field placeholders` 將各田地區裁成不同尺寸的長方形／邊界裁切田塊，以灰階區分，間隙露出下層分區作為田埂示意。

JSON 是重建來源。改 JSON 後重新執行命令；場景中的 Curve 編輯不回寫 JSON，也不會重新規劃建築盒。道路寬度在 JSON 中修改後重建；物件的 `width` 自訂屬性是來源記錄。Python 介面 `build_rural_blockout(path)` 會新增獨立集合，保留既有場景；展示腳本會將既有物件排除渲染。重複呼叫會保留不同快照，並不覆蓋前一次產物。

程式介面 `plan_building_lots` 的預設面寬 10 m、進深 13 m，尺寸變化 `variation=0.3`、退縮 2 m、間距下限 2 m。`variation=0` 固定尺寸及間距。`plan_field_parcels` 的目標田寬 28 m、田長 48 m、田埂間隙 1 m，實際尺寸依各分區範圍調整。目前這些是 Python 規劃參數，尚未提供側欄或 JSON 參數介面。

`plan_housing(layout, lots=None, wing_mix=0.65, access_width=2.0)` 將基地轉成 `HousingPlan`，包含主屋／側屋 footprint 與高度、院落、通道、道路接入及入口座標。`wing_mix=0` 關閉側屋，`wing_mix=1` 在可容納的基地全部配置側屋；基地太窄或太淺時保留單主屋。比例是種子抽樣機率，不保證精確戶數比例。若連接道路必須穿過田地或保留區，規劃會報錯，需先修改道路或分區；不會自行鋪路穿越這些區域。退縮為零時，不建立零面積的道路接入平面。

田塊細分目前只接受凸形田地區；凹形需先拆成凸形來源區。田地與道路仍以高低分層的平面灰模重疊呈現，尚未扣除道路範圍，因此此田塊資料不可直接當作作物種植範圍。道路交會處也未建立正式路口拓撲。住宅已能組成 L 形主屋／側屋與前院，但仍使用矩形基地，尚無楔形地籍、前後排共用通道、車輛迴轉空間、院牆與實際門窗／屋頂資產。需先核對外圍彎道、聚落密度、空地比例與田地分布；構圖確認後再接資產。

驗證：

```sh
python3 tests/test_rural_layout.py
python3 tests/test_rural_housing.py
blender -b --factory-startup --python-exit-code 1 --python tests/test_rural_blockout.py
blender -b --factory-startup --python-exit-code 1 --python tests/test_blender.py
```

純 Python 測試檢查路網連通、住宅分布與尺寸差異、所有道路避讓、田塊容納／不重疊／無間隙時的面積守恆及種子重現。住宅測試另檢查主屋／側屋／院落面積守恆、側屋接牆、通道寬度與道路接通、左右側基地、狹窄基地退回單主屋、零退縮及拒絕穿越田地。灰模測試檢查求值後道路面積、寬度與平坦度，建築與實際路面不相交、建築彼此不穿插、入口通道不被建築阻擋、分區與田塊面積、建築輪廓、Curve 編輯同步及存檔重開。測試報告寫入 `dist/rural_blockout_test_results.json`。
