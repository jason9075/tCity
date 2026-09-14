# 道路驅動農村：資產場景

灰模構圖確認後，以相同 JSON、基地與院落配置接入農村組件。範例包含 49 戶主屋、33 個側屋、33 塊田地、8,779 個作物實例及 92 根電桿，並有 61 跨架空線（每跨四條）、23 段明渠（約 1,606 m）、14 處安全田界轉角接合、4 處地下箱涵（約 25.6 m）及 8 座接入井。住宅的 82 個可見量體、92 根電桿與 244 條架空線現在由 Geometry Nodes 實例／曲線層生成。

```sh
blender -b --factory-startup --python-exit-code 1 --python scripts/build_rural_blockout.py -- --assets --render
```

- `dist/TCity_Rural_Settlement.blend`：包含來源分區、道路 Curve、住宅與公用設施 Geometry Nodes、作物實例及五部相機。
- `renders/rural_scene_aerial.png`：全區空拍。
- `renders/rural_scene_plan.png`：俯視配置。
- `renders/rural_scene_housing.png`：住宅與前院近景。
- `renders/rural_scene_irrigation.png`：灌溉渠近景；先生成場景，再執行下列命令，可加入第四部相機並保存。此命令直接開啟存檔，不匯入外掛，亦用於檢查封裝資源。
- `renders/rural_scene_culvert.png`：道路涵管兩端接入井近景；同一命令會加入第五部相機。涵管本體埋於路面下，可在 Outliner 的 `Rural road culverts` 集合選取查看。

```sh
blender -b --factory-startup --python-exit-code 1 --python scripts/render_rural_services.py
```

原有 `TCity_Rural_Blockout.blend` 和灰模預覽保持獨立；省略 `--assets` 仍建立灰模。`--layout` 可指定其他來源 JSON。光照使用專案既有 HDR，存檔時封裝到場景，無需連線下載資源。

## 接入方式

住宅重用 `rural_assets` 的牆面開口、窗戶和斜屋頂函式，以及既有材質、水塔和冷氣組件，依已確認的主屋／側屋可用範圍組裝。既有 `village_home` 和 `farmhouse` 整組資產自帶院落，直接縮放會覆蓋目前的前院，因此此場景使用組件介面。主屋依類型使用 RC 平屋頂、磚牆斜屋頂或鐵皮組合；側屋使用較低鐵皮屋頂。磚屋目前是紅色斜屋頂示意，尚非完整傳統瓦片模型。

住宅配置已接入 `Rural housing / GN points` 與 `Rural housing instancing` 節點群組。輸入點的 `rural_asset_index` 選取 `Rural GN housing assets` 集合內的來源 mesh，`rural_rotation` 控制每戶朝向；來源集合在視窗和渲染中隱藏，只由 Geometry Nodes 讀取。來源 mesh 目前仍由 Python 依每個預留量體組裝一次，以保留不同門口位置、尺寸和入口驗證；住宅位置與朝向則由 GN 實例層處理，後續可再把相同類型收斂成少量可縮放資產。

屋簷、排水管、水塔、冷氣均限制在原建築量體範圍內。主屋入口依院落通道位置調整，在實際牆面開孔；2 m 步行通道與院門保持原配置。`asset_kind` 記錄住宅種類，`asset_door` 記錄實際入口位置，其餘 `source_id`、`building_part`、道路與分區屬性沿用灰模資料。

稻作、成熟稻作及蔬菜直接引用 `ensure_farm_assets()` 的既有網格，以 Geometry Nodes 實例放置；土壤、水田與田埂沿用農田材質。種植點根據完整作物水平半徑預留田界、道路與電桿周邊空間，不僅檢查作物中心。休耕與蓄水田保留地表材質。

電桿直接共用 `ensure_street_assets()['Pole']` 的網格，沿道路一側配置，保留固定公尺尺寸。配置時避開全部道路、房屋、入口通道、保留區及邊界，並避免鄰近路段重複放置。規劃出的點與朝向輸入 `Rural utility poles / GN points`，由 `Rural poles / Geometry Nodes` 將既有 `Pole` 資產實例化；原始規劃物件保留為隱藏的驗證來源。

## 重建與限制

`tcity.rural_scene.build_rural_scene(path, crop_spacing=1.25, pole_spacing=32.)` 新增獨立集合。作物間距目前至少 0.8 m；電桿規劃間距至少 10 m，32 m 是分段取樣目標，遇到障礙會略過，並不保證相鄰電桿最大跨距。

JSON 是重建來源。道路 Curve 編輯只即時更新路面；住宅 GN 輸入點、電桿 GN 點與架空線 GN 曲線的移動會即時更新幾何，但改變住宅基地尺寸、來源 mesh、作物、電桿規劃或線路避讓規則仍需重新執行生成。場景中的編輯不會回寫 JSON。這個流程尚未接入側欄，也不改變舊農地生成器或舊場景的升級方式。

已加入架空線與田界明渠。架空線連接同一道路上相鄰的既有電桿，三條上層線與一條下層線的兩端對準絕緣子／支架，預設垂度 0.55 m、最大跨距 40 m；過長或投影跨越住宅／入口的線段略過，不跨道路編號自動接網。244 條線材路徑輸入 `Rural overhead wires / GN paths`，由 Curve to Mesh 生成可見線材；原始逐線 mesh 保留為隱藏驗證來源。`build_rural_scene` 可用 `cable_sag`（0–1.5 m）與 `max_wire_span`（5–60 m）調整；目前是視覺生成參數，非電力工程設計。

灌溉渠沿四個原始田地分區的外框生成，寬 0.8 m，包含混凝土槽底、側壁及低於渠頂的水面。渠頂高 0.5 m、水面高 0.28 m。遇房屋、入口、電桿或邊界便保留缺口，作物亦避開渠體；相鄰直線段在道路、住宅、入口、電桿和保留區都通過檢查的田界頂點延伸至同一位置，形成 14 處可重建的轉角接合。仍未做取水口、坡降或水流連通模擬；不是完整的灌溉水網。

`rural_culverts.py` 在同一田界邊上搜尋相鄰明渠的道路缺口；符合長度與避障條件時，縮短明渠末端並加入兩座 0.8 m 接入井及地下箱涵。涵管內淨寬 0.56 m，底面高 -0.60 m、內頂高 -0.18 m，外頂 -0.06 m，低於道路。接入井保留低於明渠槽底的通道，並切除其範圍內的地表／田地平面，避免井內被原地面封住。地下箱涵不會在路面生成凸起。超長、過短或有其他障礙的缺口仍保留，不強行接通。

這是明渠—接入井—地下箱涵的視覺幾何銜接，未計算水壓、排水能力、地形坡降或實際流向。資產場景的地表平面會因接入井而切割；原始 JSON 分區及獨立灰模不受影響。

架空線與水渠屬於重建結果，修改道路／電桿後需重新生成。尚無院牆、共用院落與前後排住宅。田地平面仍位於道路下方，作物已避路，但尚未做道路範圍的精確田地差集。建築細節以中遠景為主，尚非照片級重建。

## 驗證

```sh
blender -b --factory-startup --python-exit-code 1 --python tests/test_rural_scene.py
blender -b --factory-startup --python-exit-code 1 --python tests/test_rural.py
blender -b --factory-startup --python-exit-code 1 --python tests/test_blender.py
```

資產場景測試驗證所有建築求值後的頂點落在預留量體內、49 戶實際門口對準通道、電桿不占用路面／房屋／入口，以及全部作物實例留在田界內並避開道路。另檢查存檔重開後實例仍完整。報告寫入 `dist/rural_scene_test_results.json`。

設施檢查包含實際線材端點與電桿錨點距離、垂度、淨高與房屋避讓；明渠檢查包含底板／側壁／水面、由上向下的射線可見水面、道路與入口避讓，以及作物不穿入渠體。

涵管另檢查頂部低於道路、兩端與明渠的長度銜接、接入井避開路面，以及水面下方射線能到達井底而不命中原地面；存檔重開後仍保留涵管。
