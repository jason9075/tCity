"""Optional build-only dependency: fonttools. Runtime needs only Blender."""
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont

root=Path(__file__).resolve().parents[1]
font=TTFont('/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',fontNumber=3)
options=subset.Options();options.name_IDs=['*'];options.name_legacy=True;options.name_languages=['*']
sub=subset.Subsetter(options=options)
sub.populate(text='永和豆漿阿春機車行日日茶行金興五金幸福便當南光藥局')
sub.subset(font)
# Reserved-font-name requirement: rename this derivative subset.
for rec in font['name'].names:
    if rec.nameID in (1,4,6,16):
        rec.string=('TCitySigns' if rec.nameID==6 else 'TCity Signs').encode(rec.getEncoding())
dest=root/'tcity'/'fonts';dest.mkdir(exist_ok=True)
font.save(dest/'TCitySigns.otf')
(dest/'OFL.txt').write_text(Path('/usr/share/licenses/noto-fonts-cjk/LICENSE').read_text())
print('Subset font saved', (dest/'TCitySigns.otf').stat().st_size)
