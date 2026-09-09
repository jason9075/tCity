# TCity 0.4 · 台北道路與沿街設施

Blender 5.2 LTS extension。Preferences → Get Extensions → Install from Disk 安裝 ZIP 並啟用。

3D View → N → TCity，可新增街區、從選取的局部 XY 已填面 Mesh 生成、換種子、升級舊街區與建立實體網格複本。

預設 4–5 層台北老公寓，包含內縮陽台、鐵窗、冷氣、雨遮、小磁磚、店面入口與屋頂生活空間。

- **住宅頂樓加蓋比例 / Rooftop Addition Mix**：0–1，預設 0.85。設為 0 仍保留樓梯間、水塔。預設比例是美術設定，不是都市統計。
- **獨棟鐵皮屋比例 / Metal Shed Mix**：0–1，預設 0。六種單層浪板小工廠／倉庫不受住宅樓層控制，也不另外加住宅頂加。
- **Rooftops**：同時控制頂加與屋頂設備；獨棟鐵皮屋的主屋頂保留。
- **升級街區**：支援 0.1／0.2／0.3，保留區域與控制值。舊節點樹和資產保留，但自訂節點改動不合併。
- **建立實體網格複本**：保留來源，產生初始隱藏的網格。這不是材質貼圖烘焙。

Geometry Nodes 即時配置道路與建築；同一檔案多個區域共用原創資產。平面區域可含凹角及真正留空的孔洞，使用前套用縮放。建議 100–200 m 區域，新增區域最大 1,000 m。尚無曲線道路、坡地或轉角專用建築。

這是朝寫實方向開發的程序化原型，並非掃描資產或照片級資產庫，亦非 iCity 官方產品。程式與原創模型 GPL-3.0-or-later；招牌字型 SIL OFL（fonts/OFL.txt）；Poly Haven 照明 HDRI 為 CC0（environment/CREDITS.txt）。


0.4 新增實體瀝青道路、人行道、路緣、排水格柵、人孔蓋、黑黃警示帶電桿、電信箱與架空線。道路與平台以 Geometry Nodes 布林裁切到輸入區域，包含凹角和孔洞。

- Road Surface／Sidewalks：分別開關道路和鋪面平台；Ground 是兩者的總開關。
- Sidewalk Width／Curb Height／Road Thickness：控制寬度、高度和厚度。
- Utility Poles／Telecom Cabinets／Overhead Wires：電桿、交接箱與架空線的獨立開關。
- Pole Spacing 是最大跨距；Pole Height 與 Cable Sag 同時更新線路支點與垂度。
- Cabinet Density 控制電信箱出現機率；建築 Density 不影響沿街設施。
- Road Details 控制格柵與人孔蓋，須有可見道路；關閉電桿會同步隱藏架空線。
- 「住宅街巷／地下化／道路檢視」三個預設保留邊界、種子、樓層與頂加設定。

升級保留既有數值，但新增的人行道保留寬度會改變建築位置與數量。0.3 住宅資產可共用。電線只沿同一段街廓連接，在路口或區域中斷處停止；尚無道路 Curve 輸入、跨路／接戶線、路口坡道或交通模擬。
