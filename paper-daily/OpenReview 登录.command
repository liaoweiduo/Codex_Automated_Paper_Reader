#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
./.venv/bin/python scripts/openreview_auth.py login
openreview_setup_result=$?
if [[ $openreview_setup_result == 3 ]]; then
  printf '\n如果浏览器显示官方验证页，请手动完成，然后按回车复查论文接口。'
  read -r
  ./.venv/bin/python scripts/openreview_auth.py check
fi
printf '\n按回车关闭此窗口。'
read -r
