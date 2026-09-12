# 自由曲線道路開發計畫

撰寫日期：2026-09-09。目標版本 0.5 → 0.7。本檔是開發計畫，不表示這些功能已完成；完成後對應項目要從 [`docs/roadmap.md`](roadmap.md) 的「下一階段：道路曲線與區域控制」移除，並更新 README 的「現階段範圍」。

目標是讓使用者直接畫出道路中心線，街廓、路面、人行道、沿街設施與建築全部跟著曲線生成，且維持現有的核心約束：**評估期不跑 Python，全部由 Geometry Nodes 完成**。

## 1. 現況：哪些地方把正交網格寫死了

| 位置 | 現況 | 為什麼擋住曲線 |
| --- | --- | --- |
| `tcity/nodes.py:174-175` | `px = 面寬 × 每排戶數 + 道路寬 + 2×人行道`、`py = 進深 × 2 + 後巷 + 道路寬 + 2×人行道` | 街廓是固定週期的兩個純量，沒有「路線」這個概念 |
| `tcity/nodes.py:186-187` | 基地座標 `x = bx·px + (col+0.5)·面寬 + …`、`y = by·py + …` | 位置完全由索引算術產生，只能落在軸向格線上 |
| `tcity/nodes.py:233` | `rotation = (0, 0, Facing)`，`Facing = row × π`（`nodes.py:194`） | 建築朝向只有 0° / 180° 兩種 |
| `tcity/infrastructure.py:88-91` | 路面 = 區域立體 **減去** 軸向 cube 陣列組成的人行道島 | 人行道島是 `bx·px / by·py` 的網格實例 |
| `tcity/nodes.py:77-95`（`road_material`） | 標線用 `PINGPONG(世界 XY − tc_origin, 週期/2)` 產生 | 週期函數本身就假設道路平行 X／Y 軸 |
| `tcity/infrastructure.py:110-151` | 電桿、電信箱、水溝蓋、人孔蓋位置皆為 `row_fields()` 的索引算術 | 同上 |
| `tcity/infrastructure.py:155-157` | 跨距沿 +X：`end = pos + (±spanlength, 0, 0)` | 架空線只能是軸向直線 |

唯一與網格無關、可以直接沿用的是 **區域內判斷**（`nodes.py` 第 03 段與 `infrastructure.py:117-123` 的 `inside()`）：向下 Raycast + 到邊界邊線的距離門檻，純粹吃位置，換成曲線後不用改。

但**邊界邊線的取法要改**：`nodes.py:168-171` 用 `Face Count < 2` 選邊界邊，游離邊（Face Count = 0）也會被算進去。決定 1 採用「道路畫在區域網格裡」之後，這個判斷必須改成 `Face Count == 1` 是邊界、`== 0` 是道路中心線。

## 2. 目標與非目標

**目標**

- 使用者在區域網格裡直接拉出道路中心線（游離邊），或指定外部 Curve 物件；支援多條街。
- 路面、路緣、人行道沿曲線生成，並保留現有的區域裁切（凹角、孔洞）。
- 基地沿曲線排列、建築朝向最近街道；曲率大時街屋沿曲線彎折而不是互相穿插。
- 標線、電桿、電信箱、水溝蓋、人孔蓋、架空線沿切線方向配置。
- 舊的正交模式保留，未指定曲線時行為與 0.4 完全相同（回歸測試保證）。

**非目標（本計畫外）**

- 交通模擬、號誌時制、車道數與轉彎半徑的工程規範。
- OSM／真實地籍匯入、坡地與高程取樣（roadmap 另列）。
- 立體交叉、匝道、高架橋。

## 3. 先期技術驗證（已在 Blender 5.2.1 LTS 實測）

1. **需要的節點在 5.2 都存在**：`GeometryNodeCurveToMesh`、`ResampleCurve`、`SampleCurve`、`InputTangent`、`SampleIndex`、`OffsetPointInCurve`、`SplineParameter`、`FunctionNodeAlignRotationToVector`、`AttributeDomainSize`、`FillCurve`、`TrimCurve`、`IndexSwitch`。
2. **屬性可以穿透 `Curve to Mesh` 和 EXACT 布林**。實測：在中心線點上存 `tc_u`（弧長）、在斷面點上存 `tc_profile`（斷面段編號），經 `Curve to Mesh` + `Mesh Boolean(INTERSECT, EXACT)` 之後，evaluated mesh 仍有 `tc_u`（0 → 1.58，布林新生的頂點有插值）與 `tc_profile`（0–3，四個相異值）。**這是第 4.4 節「標線改成屬性驅動」可行的前提。**
3. **`Resample Curve` 的 Mode 在 5.2 是輸入 socket（`NodeSocketMenu`），不是節點屬性**，而且值是顯示字串：`s.default_value = 'Length'`（不是 `'LENGTH'`，會丟 enum 錯誤）。`Graph.node(kind, **attrs)`（`nodes.py:21-28`）目前用 `setattr` 設屬性，這類節點必須改走 `g.put('Length', node.inputs['Mode'])`。
4. **`NodeSocketObject` 可以當 group interface socket**，且現有的 `set_control` / `get_control` / `draw_control`（`nodes.py:266-284`）走的 `mod.properties.inputs.<id>.value` 路徑對物件 socket 同樣有效（預設讀到 `None`），`layout.prop(..., 'value')` 會直接畫出物件選擇器。**輸入介面不需要重寫。**
5. `GeometryNodeProximity` 有 `Group ID` / `Sample Group ID` 輸入 — 第 4.3 節用它來判斷「有沒有別條街比自己這條更近」。
6. **「道路畫成區域網格裡的游離邊」整條管線可行**（決定 1 的依據）。實測一個 quad 區域 + 三段游離邊，跑
   `Separate Geometry(EDGE, Face Count == 0)` → `Mesh to Curve` → `Set Spline Type = CATMULL_ROM` → `Resample(Length = 1 m)` → `Curve to Mesh(寬 6 m)`，
   得到 458 面的平滑路面。注意 Catmull-Rom 會在端點外插：畫 `x ∈ [-40, 40]` 掃出來是 `[-42.2, 42.6]`，端點需要另外夾住（`Trim Curve` 或首尾各補一個重複點）。

驗證腳本放在暫存目錄，未入庫；重跑方式是把上述節點建進一個 `is_modifier` 節點樹、掛到物件上、讀 `evaluated_get(...).data.attributes`。實作第一步應該把這個 spike 固化成 `tests/test_curve_roads.py` 的第一個案例。

## 4. 架構設計

```
區域網格 ─┬─ Face Count == 1 ──► 邊界邊（既有的區域內判斷）
          └─ Face Count == 0 ──► 道路邊 ──► Mesh to Curve ──► Set Spline Type ─┐
                                                                               ├─► 中心線
Road Curves (Object socket，選配) ──► Object Info (Relative) ──────────────────┘   │
                                                                                   │
   ┌───────────────────────────────────────────────────────────────────────────────┘
   ├─ 斷面 profile ──► Curve to Mesh ──► 路面＋路緣＋人行道（含 tc_u / tc_v / tc_profile）
   ├─ 建築線（側向偏移後重取樣）──► 基地點 ──► 建築實例／沿曲線彎折
   └─ 路緣線（側向偏移）──► 電桿、電信箱、水溝蓋、架空線
```

### 4.1 輸入：道路畫在區域網格裡（主）＋外部 Curve 物件（選配）

**決定 1 已定案：主要輸入是畫在區域網格內的游離邊**，`Road Curves` 物件 socket 保留為選配。

理由：外部物件的關聯只靠 modifier 欄位維繫，使用者刪除、改名、append、或只選區域搬家都會靜默脫鉤，而 `validate_region` 只在按按鈕時檢查一次。畫在同一個網格裡則零脫鉤風險，操作心智也和面板現有的「Tab 編輯邊界」一致。iCity 用的正是 edges/faces 而非 Curve 物件（見第 9 節）。

**網格內游離邊路徑**（第 3 節驗證 6 已實測）：

- `nodes.py:168-171` 的邊界選取改成 `Face Count == 1`；另外開一支 `Face Count == 0` 取出道路邊。
- `Mesh to Curve` → `Set Spline Type = CATMULL_ROM` 把折線變平滑；端點外插要夾住。
- 想要折角路口（十字、T 字）時，使用者把 spline type 留在 POLY 即可 — 提供 `Smooth Streets` 布林 socket 控制。

**外部 Curve 物件路徑**（給要用 Bezier 手把精修的人）：

- 在 `SOCKETS`（`nodes.py:112-145`）加入 `('Road Curves','NodeSocketObject',None,None,None,'道路中心線曲線物件 / Road centre-line curve')`。`add_modifier` 會對每個 socket 呼叫 `set_control(mod, name, default)`，物件 socket 傳 `None` 可以接受；`SOCKETS` 的解包格式（`name, kind, default, min, max, desc`）不用改。
- 節點端用 `GeometryNodeObjectInfo`，`transform_space='RELATIVE'`，讓曲線物件可以自由搬移旋轉而仍與區域對齊。
- 有指定物件時取代網格內的道路邊（`Join Geometry` 兩者也可以，但先做取代，語意單純）。

兩條路徑在這裡就合流成同一份 curve geometry，第 4.2 節之後完全共用，額外成本只有一個 Switch。

`validate_region()`（`__init__.py:23-40`）要新增：道路邊不得與區域邊界共用頂點（否則邊界偵測會混淆）、外部曲線物件必須是 `CURVE` 且不能是區域自己（否則產生 depsgraph 迴圈）、Z 範圍應接近平面、總長度上限（先訂 5,000 m）。UI 面板在「街廓尺寸」區塊上方加曲線欄位、`Smooth Streets` 與提示文字。

### 4.2 道路本體：斷面 × 中心線

不再用「區域立體減去人行道方塊」，改成**程序生成一條封閉斷面 polyline，用 `Curve to Mesh` 掃出整條街**：

- 斷面點由 `Road Width`、`Sidewalk Width`、`Curb Height`、`Road Thickness` 直接算出：路面底 → 路面頂 → 路緣立面 → 人行道頂 → 人行道背面 → 回到底部。
- 每個斷面點存 `tc_profile`（0 = 瀝青、1 = 路緣混凝土、2 = 鋪磚），掃出後用 `Set Material` 依 `tc_profile` 選面，取代現在用法線 Z 判斷路緣的 hack（`infrastructure.py:93-95`）。
- 中心線先 `Resample Curve`（Length 模式，新增 `Road Resolution` socket，預設 1.0 m）並在點上存 `tc_u = SplineParameter.Length`、`tc_curve_id = 曲線索引`。
- 區域裁切維持既有語意：`Mesh Boolean(INTERSECT, EXACT)` 與區域立體（`infrastructure.py:71-79` 的 `prism()` 可直接重用）。
- 非道路地面（街廓、後巷）：區域立體 `DIFFERENCE` 路面聯集，給獨立材質與 `tc_layer = 4`。

`tc_layer` 現有語意（道路 1、人行道 2、架空線 3）維持，新增 4 = 非道路地面；0.7 再加入 5 = 停車場、6 = 口袋綠地，並在殘餘地面點域保存 `tc_block_id`。

### 4.3 基地：沿「建築線」重取樣，不是沿中心線

這是曲線化最容易做錯的地方。若沿中心線以 `面寬` 等距取樣再側向推出去，內側基地會被擠在一起、外側會拉開。正確作法是**先偏移出建築線，再沿建築線等弧長重取樣**：

1. 中心線密取樣（0.25 m）→ 用 `Curve Tangent` 求切線 `t`，側向量 `n = (−t.y, t.x, 0)`。
2. `Set Position` 偏移 `± (道路寬/2 + 人行道寬)` 得到**臨街面線**，兩側各一條。
3. 對臨街面線 `Resample Curve`（Length = `面寬`）→ 每個點就是一戶。
4. 旋轉用 `Align Rotation to Vector`（Z 軸對齊 `±n`），取代 `nodes.py:233` 的 `row × π`。
5. 現有的 `tc_parcel_id` / `tc_floors` / `tc_asset` / `tc_is_shed` 隨機邏輯（`nodes.py:208-222`）完全沿用，只是 ID 來源從 `idx` 改成沿曲線的點索引。

**剛體實例的曲率極限（必須寫進文件）**：臨街面線半徑 `r` 時，相鄰兩戶的角步距 `θ = 面寬 / r`；後緣線半徑為 `r − 進深`，可用弧長只剩 `面寬 × (1 − 進深/r)`。因此後緣互相穿插量約為 `面寬 × 進深 / r`。以預設 面寬 7.2 m、進深 14 m、可接受穿插 0.3 m 計算，需要 `r ≥ 336 m` — 也就是**剛體實例只能撐住非常緩的彎**。

所以 0.5 要提供 `Bend Buildings to Curve`（預設開）：

- 把基地點的位置改成「街道空間」座標 `(u, v)`：`u` 沿弧長、`v` 側向。
- `Realize Instances` 之後對每個頂點用 `Sample Curve`（Length 模式，輸入 `u = 該戶 u + local.x`）取得 `Position / Normal`，世界座標 = `Position + Normal × (v + local.y)`，Z 不變。
- 效果是整排街屋沿曲線彎折，沒有縫隙也沒有穿插 — 這也比較接近實際的台灣彎道街屋。
- **代價：必須 Realize，失去實例的記憶體優勢。** 面板要標示，並保留關閉選項（緩彎時關掉更省）。烘焙流程（`TCITY_OT_bake`）不受影響。

**基地排除規則**（取代現在「前後兩排」的假設）：

- 沿用既有的區域內 Raycast + 邊界距離門檻。
- 新增：對整組曲線做兩次 `Geometry Proximity`，一次不限 Group、一次 `Sample Group ID = 自己的 tc_curve_id`。若「最近任一街」明顯比「自己這條街」更近，代表被另一條街切到，刪除該戶。這同時處理了路口附近的基地重疊。
- 後巷：兩排背對背仍然成立，但只在同一條曲線的兩側之間；跨曲線的殘餘空地留給 0.7 的停車場／綠地。

### 4.4 標線：從世界座標週期改成屬性驅動

`road_material()` 目前讀 `tc_origin / tc_period_x / tc_period_y / tc_road_width / tc_markings`，改成讀 `tc_u`（沿路弧長）與 `tc_v`（離中心線的側向距離，由 `tc_profile` 對應的斷面 x 存入）：

- 雙黃線：`|tc_v| < 0.05` 且 `|tc_v| ∈ [0.10, 0.20]` 兩條。
- 停止線／斑馬線：需要「離路口多遠」這個量。**0.5 就要把 `tc_junction_dist` 這個屬性挖好**（先用 `tc_u` 距曲線端點的距離填、或直接填一個大數），0.6 路口完成後只換算法不換介面 — 否則 shader 的標線邏輯要整段重寫。
- 磨耗遮罩維持現有 noise 作法。

驗證 2 已證明這兩個屬性能通過 `Curve to Mesh` 與 EXACT 布林，shader 端讀取方式與現在的 `ShaderNodeAttribute` 完全相同。

### 4.5 沿街設施

`row_fields()`（`infrastructure.py:110-115`）那套索引算術整組換掉，改成對**路緣線**（中心線偏移 `道路寬/2 + 人行道寬/2` 等）重取樣：

- 電桿：`Resample Curve`（Length = `Pole Spacing`）→ 點；旋轉由切線得出。比現在的算術版更短也更準。
- 電信箱：同一條線另取樣、加上 `Cabinet Density` 隨機遮罩，並與電桿錯開（沿 u 加固定偏移）。
- 水溝蓋在路緣外側、人孔蓋在車道內：改成 `± n × 固定側向距離`。
- 全部沿用既有的 `inside()` 判斷與 `tc_infra_kind` 資產查表（`street_assets.py`），資產本身不用改。

### 4.6 架空線

現在的跨距是 `pos + (±spanlength, 0, 0)`（`infrastructure.py:155-156`）。改法：

- 電桿點重取樣後，用 `GeometryNodeOffsetPointInCurve`（Offset = 1）＋ `SampleIndex` 取得**下一根電桿的位置**，得到弦向量與實際跨距。
- 仍然實例化一條有拋物線垂度的線段，但用 `Align Rotation to Vector` 對齊弦方向、X 縮放為弦長。
- 邊界防護 Raycast（`infrastructure.py:159-167`）沿用，射線方向從固定 `(sign,0,0)` 改成弦方向。
- 五條導線的側向偏移改成沿 `n` 方向，而非固定 Y。

### 4.7 雙模式與相容

**決定 3 已定案：0.5／0.6 保留雙分支，0.7 收斂成單一管線。**

- 0.5／0.6：沒有道路邊也沒有指定曲線時走原本的網格分支。用 `AttributeDomainSize` 檢查道路 curve 的點數是否為 0 當開關，接 `GeometryNodeSwitch`（幾何 Switch 是惰性求值，未選中的分支不會計算）。
- 0.7：**一組等距直線曲線就是網格** — 現在的「前排 → 後巷 → 後排」結構，等同於「每條街兩側各一排、街距 `py`」。因此把網格模式改寫成內建的直線曲線產生器，砍掉舊分支，UI 參數與名稱完全不變，使用者無感。
- 收斂的動機不是評估效能（Switch 本來就惰性），而是建圖時間、節點數、維護與測試矩陣目前全部翻倍：每個新功能都要在兩條分支各做一次。
- 收斂後輸出**不會**與 0.4 逐位元相同（路口附近的基地會被 4.3 的 Group ID 規則刪掉），回歸測試要從逐項相等改成容差比對。
- 節點群組改名 `TCity • Taiwan District v0.5`，`upgrade_modifier()`（`nodes.py:294-299`）依名稱搬值的機制不用改，新 socket 自動取預設。
- `PRESETS`、`LABELS`（`__init__.py:104-168`）新增曲線相關項目；升級按鈕文字改 0.5。
- `bl_info['version']`、`blender_manifest.toml` 的 `version` 同步改 0.5.0。

## 5. 分期交付

### 0.5.0 — 單條／多條不相交曲線街道（本計畫主體）

| 項目 | 主要改動 | 規模 |
| --- | --- | --- |
| 道路邊擷取＋邊界偵測改寫 | `nodes.py:168-171`、`Mesh to Curve` / `Set Spline Type` | S |
| 外部曲線 socket 與驗證 | `nodes.py` SOCKETS、`__init__.py` validate/panel | S |
| 斷面掃出路面＋路緣＋人行道 | 新檔 `tcity/roads.py` | L |
| 基地沿建築線排列＋朝向 | `nodes.py` 第 02／03 段分支 | M |
| 街屋沿曲線彎折 | `roads.py` + 新 socket | M |
| 標線改屬性驅動 | `nodes.py: road_material` | M |
| 沿街設施與架空線曲線化 | `infrastructure.py` 重構 | L |
| 非道路地面層 | `roads.py` | S |
| 雙模式切換與升級路徑 | `nodes.py` | S |

**驗收條件**：在區域網格裡拉一串 S 形游離邊後，所有建築、路面、人行道、設施都在區域內；沿建築線的相鄰基地間距與 `面寬` 的誤差 < 5%；開啟彎折時相鄰街屋無穿插；不指定曲線時 `tests/test_blender.py` 與 `tests/test_infrastructure.py` 的輸出與 0.4 逐項相同。

### 0.6.0 — 路口

**決定 2 已定案：路口不進 0.5。** 路口同時打到五個子系統（路面布林與圓角、人行道斷開、標線需要真正的路口距離、四角基地抑制與轉角雙立面資產、架空線中斷），其中「轉角雙立面」是資產工作不是節點工作 — 現有 42 組資產全部單面臨街，路口做出來卻露出普通側牆會比不做更醜。iCity 做到 1.5 仍在修不同車道數與銳角路口的 bug（見第 9 節），佐證這塊會持續流血，不該和曲線基礎建設綁在同一版。


- 路面聯集（`Mesh Boolean UNION, EXACT`）讓多條街自然接合；路口附近抑制人行道與標線，加轉彎圓角。
- 存 `tc_junction_dist` 給 shader 畫停止線與斑馬線。
- 路口附近的基地由 4.3 的 Group ID 規則自動排除；補上 roadmap 已列的**轉角雙立面模組**。
- 架空線在路口中斷（沿用邊界防護的射線邏輯，改成對其他街的路面射線）。

**0.6.3 後續更新**：轉角雙立面模組已補上，但做成簡化版而非專用模型——兩片既有 `_facade()` 立面繞角落轉 90° 拼接、圓角磁磚牆角銜接（`residential.py` `build_corner()`），只處理近似直角路口（`roads.py` `_place_side()` 用crossing road 的 tangent 判斷垂直度），角地基地位置額外沿本排街道方向推出 `outer + 半棟寬` 以避開路口鋪面。已知限制：對稱十字路口的同一角可能被兩條街道各自判定為轉角而各放一棟，未做跨街道去重；細節見 [`tcity/README.md`](../tcity/README.md) 0.6.3 段落與 [`roadmap.md`](roadmap.md)。

### 0.7.0 — 街廓與地面收尾

- **已完成（0.7 開發版）— 收斂成單一管線**：網格模式改寫為內建、共用頂點的正交道路網，未提供道路輸入時也進入同一條道路驅動管線；手繪游離邊／外部 Curve 依序覆蓋 fallback，移除雙分支（決定 3）。內建直線基地不執行不必要的彎折 Realize，維持可實例化輸出。
- **已完成（0.7 開發版）— 街廓地面切分**：以凸形道路專用切割體先做 EXACT 聯集，再從區域地面扣除；內建道路可穩定切出獨立 Mesh Islands，於點域寫入 `tc_block_id`。顯示用道路斷面仍保留原本材質與路緣形狀。
- **已完成（0.7 開發版）— 空置基地用途**：通過完整容納檢查、但未由 `Density` 抽中建築的沿街基地，依 `Parking Mix` 穩定轉成停車場或口袋綠地；可由 `Open Spaces` 關閉。
- **已完成（0.7 開發版）— 曲率安全**：以前後相鄰基地的弦向量估算局部轉角。彎折模式要求曲率半徑約不小於一個 `Depth`；剛體模式依 `Depth × 單戶角度 ≤ 0.3 m` 的後緣誤差預算。超限基地不生成建築或空地資產，輸出 `tc_curvature_warning`，側欄讀取後顯示紅色警示。
- 街廓內再做面式基地切分，取代「沿線兩排」的簡化。

## 6. 測試計畫

新增 `tests/test_curve_roads.py`（沿用 `test_infrastructure.py` 的 `coverage()` / `instances()` / `digest()` 寫法，JSON 報表寫到 `dist/curve_test_results.json`）：

1. **屬性穿透**：把第 3 節驗證 2 固化成回歸測試 — 路面 evaluated mesh 必須有 `tc_u`、`tc_v`、`tc_profile`，且值域非退化。
2. **基地間距**：沿曲線相鄰基地的實際距離 ≈ `面寬`（誤差 < 5%），且到中心線的距離 ≈ `道路寬/2 + 人行道寬 + 進深/2`。
3. **無穿插**：開啟彎折時，任兩戶的實際頂點 AABB 不重疊超過 0.05 m。
4. **區域裁切**：對 L 形與帶孔區域跑 `coverage()`，所有頂點與面心都在區域內、孔外。
5. **設施**：相鄰電桿距離 ≤ `Pole Spacing`；每段架空線兩端確實落在電桿頂點附近（沿用 `anchored()` 的檢查方式）。
6. **決定性**：同一 seed 兩次評估完全相同；換 seed 改變資產但不改基地位置。
7. **回歸**：未指定曲線時，`snapshot()` 結果與 0.4 網格模式一致。
8. **錯誤輸入**：曲線指向區域自己、指向非曲線物件、曲線過長、道路邊與邊界共用頂點 → `validate_region` 要擋下。
9. **邊界偵測**：區域網格內有游離邊時，邊界邊集合必須與沒有游離邊時相同（`Face Count == 1` 的回歸測試），且既有的 L 形／孔洞測試不受影響。
10. **兩種輸入等價**：同一條路線分別用「網格內游離邊」與「外部 Curve 物件」餵入，evaluated 輸出應在容差內相同。
11. **曲率安全**：無分支的 90° 折角要略過轉角基地並輸出 UI 警示旗標；同長直線不可誤報。

既有測試同步更新：`test_upgrade.py` 加 0.4 → 0.5 升級保值；`test_package.py` 的版本字串與檔案清單；`test_demo.py` 若示範場景加入曲線街道則一併更新。`scripts/build_demo.py` 增加一個彎道相機視角，`scripts/render_streets.py` 增加彎道渲染。

## 7. 效能預算與風險

| 風險 | 影響 | 對策 |
| --- | --- | --- |
| EXACT 布林在長路網上很慢 | 互動編輯卡頓 | `Road Resolution` socket 控制掃出密度；曲線完全在區域內時跳過裁切；文件建議先用 100–200 m 區域（同 0.4） |
| 彎折建築必須 Realize，記憶體上升 | 大區域爆記憶體 | 預設可關；面板標示；維持既有烘焙流程 |
| 斑馬線／停止線在 0.5 沒有真正的路口資訊 | 標線位置只是近似 | 0.5 就建立 `tc_junction_dist` 屬性但用曲線端點距離填值，0.6 只換算法不換介面 |
| 曲率過大時基地仍可能不合理 | 視覺破圖 | **0.7 已完成**：相鄰基地弦向量估算曲率，超限基地略過並輸出 UI 警示旗標 |
| `Resample Curve` 之類節點的 Mode 變成 socket | 建圖時丟 enum 例外 | `Graph` 增加 `menu()` helper 統一處理，並在 `tests/test_curve_roads.py` 檢查 `mod.node_warnings` 為空（既有測試已有此檢查） |
| 曲線物件與區域互相參照 | depsgraph 迴圈 | `validate_region` 擋下；operator 回報錯誤 |
| 道路邊與邊界邊在同一個網格裡，使用者可能誤刪或讓兩者共用頂點 | 邊界偵測混淆、區域破損 | `validate_region` 檢查道路邊不與邊界共用頂點；面板顯示道路邊數量，異常時提示 |
| Catmull-Rom 在端點外插（實測畫 ±40 掃出 ±42.5） | 街道超出使用者預期的範圍 | 首尾各補重複點或用 `Trim Curve` 夾住；`Smooth Streets` 關閉時回到 POLY |

## 8. 已定案的決策（2026-09-09）

| # | 決策 | 結論 | 理由 |
| --- | --- | --- | --- |
| 1 | 曲線來源 | **道路畫成區域網格裡的游離邊為主，外部 `NodeSocketObject` Curve 為選配** | 外部物件只靠 modifier 欄位維繫，刪除／改名／append／單獨搬移都會靜默脫鉤；畫在同一網格裡零脫鉤，且與面板現有的「Tab 編輯邊界」心智一致。管線已實測可行（第 3 節驗證 6）。曾評估「曲線當區域的子物件」，但 GN 沒有「取得我的子物件」的節點，仍得用 Object socket 指過去，等於選項 A 多一層約束，已排除。 |
| 2 | 0.5 是否做路口 | **不做，推到 0.6；但 0.5 就要挖好 `tc_junction_dist`** | 路口同時打到路面布林、人行道斷開、標線、四角基地與轉角雙立面資產、架空線中斷五個子系統，其中轉角資產是資產工作。最小可行版（僅直角、固定圓角、轉角留空地）估計 +30～40% 工期，且空地在渲染上很明顯。 |
| 3 | 網格模式是否長期保留 | **0.5／0.6 保留雙分支，0.7 收斂成單一管線** | 一組等距直線曲線就是網格，兩者不衝突。保留雙分支的成本在建圖時間、節點數、維護與測試矩陣翻倍，不在評估效能。收斂後 UI 參數不變，使用者無感。 |

## 9. 參考：iCity 怎麼做

查證日期 2026-09-09。**iCity 的官方文件相當陽春，節點層級的作法沒有公開**，以下都是產品描述與更新日誌等級的資訊，不是實作細節。

- **輸入是 mesh 的 edges 和 faces，不是 Curve 物件**：官方原話為「Define your city layout with edges and faces. iCity's procedural systems instantly transform them into detailed buildings and streets.」
- **兩種造路方式**：用 Procedural Road 工具畫路網，或把既有街廓的 edge 擠出來長新路。
- **建築指派到面**：「選取要變成程序建築的面 → 設定樓高範圍 → 按 Assign」。face = 街廓／基地。
- **即時性**：在 viewport 直接拖動道路，建築自動重生成 — 與 tCity「無 Python handler、GN 即時評估」的取向一致。
- **路口**：有高速公路專用的 intersection presets 與 custom island 物件；1.5 的更新內容包含修正不同車道數之間的路口、以及銳角路口的 bug。
- **道路本身**：寬度、車道數、自訂車道標線與塗裝、材質，以及街道與橋樑的高程、坡度、曲線。
- **同團隊的 Parametra**（跨 DCC 版本）宣稱 roads / blocks / plots / building masses 全參數化，並可直接拉 OpenStreetMap 街網。

**不要照抄的地方**：iCity 的 face → 建築量體模型適合一面一棟的大樓，不適合連棟街屋。tCity 的核心規則是「面寬」，街廓多邊形在 tCity 只能當容器，戶的切分仍須沿臨街面線等弧長進行（第 4.3 節）。

來源：
[CG Channel · iCity 1.5](https://www.cgchannel.com/2025/06/icity-generates-procedural-3d-cities-inside-blender/) ·
[80.lv · 上市報導](https://80.lv/articles/long-awaited-procedural-city-generator-for-blender-is-now-available) ·
[80.lv · 地形與道路系統更新](https://80.lv/articles/city-generator-icity-gets-new-terrain-editing-tools-road-system-enhancements) ·
[iCity 官方使用指南](https://icity3d.com/4-user-guide-for-the-add-on-system/) ·
[iCity 文件首頁](https://icity3d.com/icity-documentation/) ·
[Parametra 首頁](https://icity3d.com/) ·
[Superhive 產品頁](https://superhivemarket.com/products/icity)

本專案不包含 iCity 程式碼或付費模型；以上僅作為架構決策的比較依據，與 [`docs/references.md`](references.md) 的立場一致。
