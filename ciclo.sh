#!/usr/bin/env bash
# Análisis continuo: analiza cada INTERVALO_MIN minutos durante ~5,6 horas y
# publica en el panel. Al terminar, el workflow se vuelve a lanzar solo.
set -u
INTERVALO=${INTERVALO_MIN:-5}
FIN=$(( $(date +%s) + ${DURACION_MIN:-335} * 60 ))
ULTIMO_PUSH=0

git config user.name "radar-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

publicar() {
  for i in 1 2 3; do
    git pull --rebase --autostash -q -X theirs && git push -q && return 0
    sleep 5
  done
  return 1
}

while [ "$(date +%s)" -lt "$FIN" ]; do
  echo "::group::Análisis $(date -u +%H:%M)"
  python main.py senales || echo "El análisis falló en esta vuelta; se reintenta en la siguiente."
  echo "::endgroup::"
  git add docs/data 2>/dev/null
  if ! git diff --cached --quiet; then
    AHORA=$(date +%s)
    # Publica de inmediato si se abrió o cerró alguna señal; si no, como máximo cada ~10 min
    # (GitHub Pages admite unas 10 publicaciones por hora).
    FIRMA=$(python -c "import json;d=json.load(open('docs/data/senales.json'));print(sorted((str(s.get('id')),str(s.get('estado'))) for s in d.get('senales',[])))" 2>/dev/null | md5sum)
    if [ "$FIRMA" != "${FIRMA_ANT:-}" ] || [ $((AHORA - ULTIMO_PUSH)) -ge 570 ]; then
      git commit -q -m "Actualizar datos del radar" && publicar && ULTIMO_PUSH=$AHORA && FIRMA_ANT=$FIRMA
    fi
  fi
  # espera hasta el siguiente múltiplo de INTERVALO minutos (+20 s)
  P=$(( INTERVALO * 60 ))
  ESPERA=$(( P - $(date +%s) % P + 20 ))
  [ $(( $(date +%s) + ESPERA )) -lt "$FIN" ] || break
  sleep "$ESPERA"
done

# último envío pendiente
git add docs/data 2>/dev/null
git diff --cached --quiet || { git commit -q -m "Actualizar datos del radar" && publicar; }
exit 0
