# 台灣農地與鄉間環境

Blender 5.2.1 LTS / TCity 0.6.2 / `TCity • Taiwan Farmland v0.2`。

## 使用

- 直接開啟 `dist/TCity_Taiwan_Farmland.blend`，選取農地物件，在修改器調參。不必執行 Python 或安裝外掛即可生成。
- 安裝 `dist/tcity-0.6.2.zip` 後：`N → TCity → 台灣農地 → 新增農地範例`。
- 使用既有區域：有面的局部 XY 平面網格 → 套用縮放 → `從選取區域生成農地`。不規則外框、凹角、分離島與真正的面孔洞都可使用。
- 本機可執行 `./scripts/open_farmland.sh` 開啟示範並載入側欄，不修改使用者偏好設定。
- 舊農地的側欄顯示「升級農地 · 農舍、樹林與電桿」；升級保留既有控制值、原區域與舊節點群組。城市節點群組仍使用 v0.6。

## 控制

| 項目 | 行為 |
| --- | --- |
| Seed | 同時改變共享田界與用途；同一種子可重現 |
| Plot Width / Length、Irregularity | 平均田區尺寸與田形變化 |
| Field Angle | 整組自動田格相對外框的角度 |
| Bund Width | 名目田埂寬度，隨田形稍有變化 |
| Rice Mix / Ripening | 稻菜分配及綠稻／金黃稻比例 |
| Orchard / Fallow / Flooded / Structure / Woodland Mix | 分配果園、休耕、蓄水田、農業設施與自然林地 |
| Crops / Plant Spacing | 稻菜、果樹、田埂草的顯示與稻菜間距 |
| Structures | 顯示模型；關掉仍保留設施用地，要還原為農地請將 Structure Mix 設為 0 |
| Trees | 控制自然闊葉木與竹叢；不影響行列果園 |
| Farm Roads / Road Width | 自動田界農路與寬度；關閉也會移除沿路電桿及線路 |
| Irrigation | 實體槽底、側壁和水面的開口灌溉渠 |
| Utility Poles / Pole Spacing | 路緣混凝土桿；每個有效農路段的最大跨距 |
| Overhead Wires / Cable Sag | 三條上層線和一條較低通訊線；關閉電桿會一起關閉線路 |

用途是**依序的條件機率**，不是需加總至 100% 的面積百分比。後分配的用途優先順序為設施、樹林、果園、休耕、蓄水，再以 Rice Mix 分配稻菜。固定種子的有限田塊不保證恰好符合輸入比例。

三種預設為水稻田、混合耕作、農工交錯；可再調自然樹林比例。農舍包含磁磚 RC 住宅、紅磚平房、L 形院落住宅；另有鐵皮農用棚與栽培隧道。電桿高度固定 9 m。

## 幾何與效能

Python 只在建立節點群組和原創資產時執行；參數更新完全由 Geometry Nodes 評估。田面、田埂、農路和明渠是實體網格，植物與建築保留實例。較大區域會自動增加稻菜間距，候選格點預算約十八萬；這是單層候選格點預算，並非整個場景的總頂點數限制。

作物依裁切後田面的用途採樣；果樹和樹林有樹冠退縮，農舍以完整外接半徑判斷能否放下。無法容納完整模型的小用地仍會保留地面。電線跨越孔洞或區域外時整段略過，即使兩端電桿原本可以落在區域內。

`建立實體網格複本` 會 Realize Instances 並保留原始程序物件；複本初始隱藏，避免重疊。大面積農田實體化會增加記憶體需求。

## 現階段範圍

這版是平地中遠景的合成鄉村模型。外框可以自由修改；內部仍是共用頂點的變形田格與自動農路，尚未實作任意地籍多邊形、逐面手動分割、手繪農路或坡地梯田。不是將照片投影在平面上，也不是照片掃描級的近景資產。

實景照片與建模對應見 [鄉村實景研究](research/rural-landscape.md)。示範檔中的四台相機僅供檢查，使用者不需逐一查看才能操作。

## 重建與檢查

```sh
blender -b --factory-startup --python-exit-code 1 --python scripts/build_farmland_demo.py -- --render
blender -b --factory-startup --python-exit-code 1 --python tests/test_farmland.py
blender -b --factory-startup --python-exit-code 1 --python tests/test_rural.py
blender -b --factory-startup --python-exit-code 1 --python tests/test_farmland_demo.py
```

本機系統套件若缺 `cattrs`，加上 `--python-use-system-env`，並將 `PYTHONPATH` 指向專案 `.venv/lib/python3.14/site-packages`。一般官方 Blender 安裝不需此工作站專用設定。
