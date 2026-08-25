# Corpus

Los documentos **no se versionan**. `.gitignore` excluye todo este directorio
salvo este archivo.

## Por qué

Dos razones, y las dos importan.

**Legal.** Los documentos de un dominio clínico rara vez son de libre
redistribución. Publicar un PDF de un tercero en un repositorio público es
distribuirlo, aunque el propósito sea demostrar una arquitectura.

**Privacidad.** Documentación institucional real puede contener nombres de
profesionales, números de matrícula, direcciones de sedes o datos de
pacientes. Nada de eso tiene por qué terminar en GitHub para demostrar que un
sistema de recuperación funciona.

Lo que se publica es la arquitectura, las decisiones y los resultados de
evaluación. El corpus se describe; no se adjunta.

## Qué poner acá

Archivos `.md` o `.txt` en UTF-8. La segmentación usa los encabezados para
determinar la sección de cada fragmento, así que conviene que los documentos
los tengan: `#`, `##`, o títulos en mayúsculas sobre línea propia.

Si el material original está en PDF, hay que convertirlo a texto antes. La
conversión no forma parte de este repositorio a propósito: mezclar extracción
de PDF con recuperación hace que, cuando algo falla, no se sepa cuál de las
dos capas falló.

## Origen del corpus usado

Catorce documentos de procedimientos y derechos en atención ambulatoria,
redactados a partir de información pública de organismos e instituciones
sanitarias de Argentina, consultada en agosto de 2026.

### Laboratorio de análisis clínicos

`laboratorio-extracciones.md` — horarios, ayuno según edad, documentación,
recepción de muestras y entrega de resultados.
Fuente: [Laboratorio, Hospital Nacional Posadas](https://www.argentina.gob.ar/salud/hospital-nacional-posadas/laboratorio)

### Atención odontológica

`odontologia-admision-turnos.md` · `odontologia-especialidades.md` — primera
consulta, admisión, solicitud de turnos, aranceles, especialidades y
diagnóstico por imágenes.
Fuentes: [Hospital Odontológico UNC](https://hospital.odo.unc.edu.ar/) · [Pacientes, Facultad de Odontología UNC](https://www.odo.unc.edu.ar/pacientes)

`odontologia-atencion-general.md` — población atendida, días y horarios,
urgencias y equipo profesional.
Fuente: [Odontología, Hospital Nacional Baldomero Sommer](https://www.argentina.gob.ar/salud/hospitalsommer/especialidades/odontologia)

### Derechos del paciente

`derechos-atencion-y-trato.md` · `derecho-a-la-informacion.md` ·
`consentimiento-informado.md` · `historia-clinica.md` · `confidencialidad.md` ·
`directivas-anticipadas.md` — derecho a la asistencia y al trato digno,
información sanitaria, consentimiento informado, acceso y plazos de la
historia clínica, reserva de la información, y directivas anticipadas.
Fuente: [Ley simple: Derechos del paciente — Ministerio de Justicia](https://www.argentina.gob.ar/justicia/derechofacil/leysimple/derechos-del-paciente) (Ley 26.529)

`obligaciones-del-paciente.md` — colaboración con el tratamiento, trato hacia
el personal, cuidado de instalaciones, firma de documentación e información
veraz.
Fuente: [Derechos y obligaciones del paciente, Hospital Argerich](https://buenosaires.gob.ar/gcaba_historico/hospitalargerich/informacion-para-pacientes/derechos-y-obligaciones-del-paciente)

### Vacunación

`vacunacion-acceso-y-gratuidad.md` · `vacunacion-obligatoriedad.md` ·
`carnet-de-vacunacion.md` — gratuidad y alcance, dónde vacunarse,
obligatoriedad y responsables, ausencia laboral justificada, carnet unificado
y registro digital.
Fuente: [Ley simple: Vacunación — Ministerio de Justicia](https://www.argentina.gob.ar/justicia/derechofacil/leysimple/vacunacion) (Ley 27.491)

---

## Tratamiento aplicado

El contenido se normalizó a una estructura común de encabezados, porque la
segmentación los usa para determinar la sección de cada fragmento.

Se quitaron nombres de profesionales, números de teléfono y direcciones de
correo. El sistema no necesita datos identificatorios para demostrar que
recupera y cita bien, y conservarlos habría sido incorporar información
personal sin motivo.

Los circuitos descritos —ayuno según edad, documentación obligatoria, estudios
que requieren turno previo, plazos de entrega de la historia clínica— son
genéricos de cualquier centro de atención ambulatoria. El sistema no está
atado a ninguna institución en particular.
