#!/bin/bash
# Reexecutável: prepara somente a venv e não apaga dados do usuário.
set -euo pipefail

workspace_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
project_root="$workspace_root/job-radar-pilot"
upstream_root="$workspace_root/vendor/Scrapling"
python313="${JOBRADAR_PYTHON:-python3.13}"
expected_tag="v0.4.15"
expected_commit="333fa22b7a5821194ce66b59b11f4b16a6484f02"

fail() { echo "Falha: $*" >&2; exit 1; }
command -v "$python313" >/dev/null 2>&1 || fail "Instale Python 3.13 ou defina JOBRADAR_PYTHON com seu caminho."
"$python313" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)' || fail "O Radar exige Python 3.13."
command -v git >/dev/null 2>&1 || fail "Instale o Git (ferramentas de linha de comando do macOS)."

if [[ ! -e "$upstream_root" ]]; then
    mkdir -p "$workspace_root/vendor"
    git clone --depth 1 --branch "$expected_tag" https://github.com/D4Vinci/Scrapling.git "$upstream_root"
fi
[[ -d "$upstream_root/.git" ]] || fail "Scrapling existente sem clone Git; confira $upstream_root."
origin="$(git -C "$upstream_root" remote get-url origin)"
[[ "$origin" == "https://github.com/D4Vinci/Scrapling.git" || "$origin" == "https://github.com/D4Vinci/Scrapling" ]] || fail "Origem inesperada do Scrapling: $origin"
[[ "$(git -C "$upstream_root" describe --tags --exact-match)" == "$expected_tag" ]] || fail "O Scrapling deve estar fixado em $expected_tag."
[[ "$(git -C "$upstream_root" rev-parse HEAD)" == "$expected_commit" ]] || fail "Commit inesperado do Scrapling."

venv_python="$project_root/.venv/bin/python"
if [[ ! -x "$venv_python" ]]; then
    "$python313" -m venv "$project_root/.venv"
fi
"$venv_python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)' || fail "A venv existente não usa Python 3.13; preserve seus dados e recrie somente .venv."
"$venv_python" -m pip install --upgrade pip
"$venv_python" -m pip install -e "$upstream_root[fetchers]" -e "$project_root[test]"
"$venv_python" -c 'import importlib.metadata as m; assert m.version("scrapling") == "0.4.15"'
"$project_root/.venv/bin/scrapling" install
"$venv_python" -m pip check

shortcut_dir="${JOBRADAR_SHORTCUT_DIR:-$HOME/Desktop}"
shortcut="$shortcut_dir/Radar de Vagas.command"
mkdir -p "$shortcut_dir"
printf '#!/bin/bash\nset -euo pipefail\nexec %q\n' "$workspace_root/Radar de Vagas.command" > "$shortcut"
chmod 755 "$shortcut"

echo "Radar preparado com Python 3.13 e Scrapling $expected_tag ($expected_commit)."
echo "Atalho instalado em $shortcut"
