#!/usr/bin/env bash
# Regenera el modelo scorer desde cero (~4h en CPU 16 cores, ~2h en 4 cores).
#
# Este script SOLO es necesario si quieres re-entrenar (por ejemplo, para
# añadir más semillas, probar otras features, o validar que el pipeline es
# reproducible). Los artefactos resultantes ya están versionados en este repo:
#   - labels/planes.jsonl    : 600 planes CP-SAT (665 KB)
#   - models/scorer_full.txt : modelo LightGBM LambdaRank (2.7 MB)
# Puedes usar el scorer directamente sin correr este script.
#
# Requisitos:
#   - Python 3.10+
#   - ortools (solo para el etiquetado CP-SAT)
#   - lightgbm + numpy (para entrenar_variantes.py)
#
# Pasos:
#   1. Etiquetar 600 escenarios (semillas 20300–20899) con CP-SAT.
#   2. Entrenar el scorer LambdaRank (variante binaria, features locales+globales).
#   3. (Opcional) Validar fuera de muestra contra el motor determinista.
#
# Uso:
#   bash ml/build_scorer.sh

set -euo pipefail

cd "$(dirname "$0")/.."   # raíz del deliverable

echo "==> [1/3] Etiquetando 600 escenarios con CP-SAT (~4 h en 16 cores)..."
echo "        (semillas 20300-20899, tope 90 s/escenario)"
python3 ml/etiquetar_cpsat.py \
    --desde 20300 --hasta 20899 \
    --tope 90 \
    --salida labels/planes.jsonl

echo "==> [2/3] Entrenando scorer (LambdaRank, features locales+globales)..."
python3 ml/entrenar_variantes.py \
    --planes labels/planes.jsonl \
    --max-seeds 600 \
    --salida-dir models

# Renombrar al nombre que solver_scorer.py busca por defecto
if [ -f models/scorer_binario.txt ]; then
    cp models/scorer_binario.txt models/scorer_full.txt
    echo "==> Modelo guardado en models/scorer_full.txt"
fi

echo "==> [3/3] Validando fuera de muestra (1200 semillas)..."
echo "        (esto puede tardar ~30 min; saltarlo con Ctrl-C si no se necesita)"
python3 ml/bench_estratificado.py 1200 5001

echo
echo "Listo. El runtime puede usar el scorer vía:"
echo "    SCORER_MODEL=models/scorer_full.txt python3 ml/solver_scorer.py"
