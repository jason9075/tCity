# TCity 0.6.4 · 台灣新式住宅社區

直接開啟 [TCity_Modern_Communities.blend](../dist/TCity_Modern_Communities.blend)。節點與原創模型已存入檔案；不用啟動 Python，就能在 Modifier Properties 即時修改。已實測 Blender 5.2.1 LTS。

安裝 [tcity-0.6.4.zip](../dist/tcity-0.6.4.zip) 後，在 `3D View → N → TCity → 新式住宅社區` 選「新增住宅社區範例」，或對自己的已填面 XY 平面區域執行「從選取區域生成新式社區」。先套用物件縮放，1 unit = 1 m；區域不要帶其他修改器或游離邊。

## 建築與配置

包含單棟、雙棟和弧邊大陽台住宅。每棟有高一樓入口基座、內縮陽台、金屬／玻璃欄杆、門窗、側背面冷氣遮屏、屋突與水塔設備。基地含庭院步道、草地、樹池、座椅、信箱和停車入口構件。道路、人行道、標線、排水、人孔蓋、電信箱跟著社區尺度生成。

| 控制 | 行為 |
| --- | --- |
| Seed | 固定邊界與設定能重現類型、樓高和空置配置 |
| Density | 整個社區基地的出現機率；0 仍保留街道 |
| Community Width / Depth | 預設 60 × 48 m，寬 52–90 m、深 42–80 m；整組 XY 縮放，含建築、棟距與庭院 |
| Min / Max Floors | 主要塔樓 6–24 層（含一樓），上下限填反也可；首層 4.5 m，上層各 3.1 m，沒有整棟垂直拉伸 |
| Twin Community Mix | 非大陽台基地之中的雙棟機率；主棟至少 8 層時，副棟低兩層 |
| Green Balcony Mix | 大陽台類型的機率，優先於雙棟判斷；並非全台住宅的統計比例 |
| Buildings | 開關整組建築、基座與庭院硬體 |
| Landscape | 單獨控制庭園樹木，需開啟 Buildings；樓層盆栽及草地仍屬建築模組 |
| Road / Sidewalk Width | 道路 6–24 m、人行道 1–4 m，同步重排社區基地 |
| Ground / Road Markings / Road Details / Telecom Cabinets | 街道地面、標線、排水與人孔、沿街箱體分項控制 |

三個預設「單棟／雙棟／大陽台」修改類型比例與樓高上下限，保留邊界、種子、道路和密度。道路採無架空電線的社區配置；若需鄉間電桿和架空線，農地生成器已有對應控制。

## 不規則區域

Tab 編輯外框，離開編輯模式即更新。可用凹形、分離島嶼及由周圍面片真正留空的孔洞。完整社區基地碰到邊界或孔洞就整組略過，包含塔樓以外的庭院也要放得下。小區域可能只有道路；不會把大樓切成半棟。

道路方向跟隨物件局部 X/Y 軸。移動、旋轉物件會帶著整個社區移動。改變外框包圍盒或模組尺寸會重排候選基地。最多評估 400 個候選社區；建議先用約 150–250 m 區域，從低樓層開始。實體化所有樓層會增加記憶體用量。

新式社區目前使用獨立節點群組 `TCity • Modern Taiwan Communities v0.1`，沒有自動混排舊街屋、跟隨手繪曲線道路、地籍匯入或坡地適配。

## 儲存、烘焙與檢查

「建立實體網格複本」保留原程序物件，另建隱藏的 Baked 網格，避免重疊。材質仍是 Blender 程序 shader；輸出遊戲引擎需另做材質烘焙。

範例含社區全景、入口、陽台三台相機，照明 HDRI 已封裝。此工作站可用 `./scripts/open_modern.sh` 載入檔案及當次側欄。`scripts/build_modern_demo.py -- --render` 重建並渲染；`scripts/render_modern.py` 渲染已存檔案；加 `-- --view=balconies` 可只渲染陽台，另有 `overview`、`entrance`。

實景出處、套用對照與目前精度限制見 [住宅研究](research/modern-residential.md)。測試涵蓋完整基地、孔洞、凹角、變形及移動後的實際頂點、樓層組合、開關、獨立開檔與打包。

驗證報告：[社區幾何與配置](../dist/modern_test_results.json)、[不載入外掛的開檔測試](../dist/modern_demo_test_results.json)、[ZIP 隔離測試](../dist/package_test_results.json)。
