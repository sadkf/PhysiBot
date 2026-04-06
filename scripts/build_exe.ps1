# 将来用于 PyInstaller 打包「单文件 exe」占位脚本。
# 完整打包需处理隐藏导入、资源文件与 embedded 路径；当前推荐用户用 PhysiBot.cmd + 已安装 Python。
#
# 参考命令（需自行调试）:
#   pip install pyinstaller
#   cd <项目根>
#   pyinstaller --onefile --name PhysiBot --paths src -m physi_core
#
# 或使用 cx_Freeze / Nuitka 等方案。

Write-Host "单文件 exe 打包尚未在本仓库自动化；请使用 PhysiBot.cmd 或 uv run python -m physi_core。" -ForegroundColor Yellow
exit 0
