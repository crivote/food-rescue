#!/usr/bin/env bash
# Regenera el modelo scorer (labels/scorer_binario.txt) desde cero.
#
# Requisitos:
#   - Python 3.10+
#   - ortools (solo para el etiquetado CP-SAT)
#   - lightgbm + numpy (para entrenar_variantes.py)
#   - ~2 horas de CPU en 4 cores (mediana 12 s/escenario, 600 escenarios)
#
# Pasos:
#   1. Etiquetar 600 escenarios (semillas 20300–20899) con CP-SAT.
#      Output: labels/planes.jsonl (~600 KB)
#   2. Entrenar el scorer LambdaRank (variante binaria, features locales+globales).
#      Output: labels/scorer_binario.txt (~2.7 MB)
#   3. (Opcional) Validar fuera de muestra contra el motor determinista.
#      Output: tabla por cuartil en stdout
#
# Uso:
#   bash ml/build_scorer.sh
#
# Si quieres apuntar el runtime a otra ruta, exporta SCORER_MODEL:
#   export SCORER_MODEL=/otra/ruta/scorer.txt
#   python3 ml/solver_scorer.py  # consumirá $SCORER_MODEL

set -euo pipefail

cd "$(dirname "$0")/.."   # raíz del deliverable

echo "==> [1/3] Etiquetando 600 escenarios con CP-SAT (~2 h)..."
echo "        (semillas 20300-20899, tope 90 s/escenario)"
python3 ml/etiquetar_cpsat.py \
    --desde 20300 --hasta 20899 \
    --tope 90 \
    --salida labels/planes.jsonl

echo "==> [2/3] Entrenando scorer (LambdaRank, features locales+globales)..."
python3 ml/entrenar_variantes.py \
    --planes labels/planes.jsonl \
    --max-seeds 600 \
    --salida-dir labels

# Renombrar al nombre que solver_scorer.py busca por defecto
if [ -f labels/scorer_binario.txt ]; then
    cp labels/scorer_binario.txt labels/scorer_full.txt
    echo "==> Modelo guardado en labels/scorer_full.txt y labels/scorer_binario.txt"
fi

echo "==> [3/3] Validando fuera de muestra (1200 semillas)..."
echo "        (esto puede tardar ~30 min; saltarlo con Ctrl-C si no se necesita)"
python3 ml/bench_estratificado.py 1200 5001 \
    --modelo labels/scorer_binario.txt

echo
echo "Listo. El runtime puede usar el scorer vía:"
echo "    SCORER_MODEL=labels/scorer_full.txt python3 ml/solver_scorer.py"
