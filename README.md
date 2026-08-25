# Asistente de consulta sobre documentación institucional de salud

Un sistema que responde preguntas sobre la documentación de un centro de salud
—turnos, requisitos de admisión, preparación para estudios, derechos del
paciente— y **cita de qué documento sacó cada respuesta**.

Construido sobre Azure OpenAI y Azure AI Search, desplegados desde Azure AI
Foundry. Aplicación en Python.

---

## Qué hace

Una persona pregunta *"¿cuántas horas de ayuno necesito para un análisis de
sangre?"* y el sistema responde *"12 horas"*, indicando el documento y la
sección exactos de donde salió el dato.

Y si pregunta algo que la documentación no cubre —*"¿cuánto cuesta el
estudio?"*— responde que no tiene esa información, en lugar de inventar una
respuesta plausible.

Esa segunda parte es el punto del proyecto.

---

## Por qué eso es difícil

Un modelo de lenguaje siempre produce una respuesta. Si no encuentra el dato,
lo completa con algo que suena razonable. En un buscador de recetas eso es un
inconveniente; en documentación de salud, es un problema serio: alguien puede
presentarse sin ayuno, sin la documentación necesaria, o creer que tiene un
derecho que no tiene.

Por eso el criterio de aceptación de este sistema no es que responda bien. Es
que **se calle cuando no sabe**, y que todo lo que afirme sea verificable
contra un documento.

Para comprobar que eso realmente pasa, 11 de las 42 preguntas de prueba son
preguntas **sin respuesta en la documentación**, escritas a propósito con
el mismo vocabulario que el resto — de modo que suenen como si la respuesta
tuviera que estar. Si el sistema contesta alguna, está inventando.

---

## Qué se usó

| Componente | Servicio |
|---|---|
| Modelo de lenguaje | Azure OpenAI — `gpt-5.4-mini` |
| Vectorización de texto | Azure OpenAI — `text-embedding-3-small` |
| Índice y búsqueda | Azure AI Search |
| Aplicación | Python 3.12 |

Los modelos se eligieron consultando el calendario oficial de retiros de
Azure: ambos están en soporte general, no en estado deprecado. La opción por
defecto en la mayoría de los ejemplos que circulan, `gpt-4o-mini`, figura como
deprecada y desplegarla habría significado heredar una migración desde el
primer día.

---

## Resultados

Corrida del 25 de agosto de 2026, sobre 42 preguntas.

| Métrica | Resultado |
|---|---|
| Respondió correctamente lo que estaba documentado | 31 / 31 |
| Se abstuvo cuando la respuesta no estaba | 11 / 11 |
| Citó la fuente en cada respuesta | 31 / 31 |
| Acertó el dato pedido, no solo respondió algo | 31 / 31 |

De las 11 abstenciones, **3 se resolvieron sin llegar a invocar al modelo**: el
filtro de relevancia las frenó antes, lo que ahorra la llamada y elimina la
posibilidad de inventar.

Corpus: 14 documentos, 60 fragmentos, de fuentes públicas citadas en
[`corpus/README.md`](corpus/README.md).

Los resultados caso por caso están en
[`resultados-evaluacion.json`](resultados-evaluacion.json).

Un 100% con un corpus de este tamaño dice menos de lo que parece, y conviene
leerlo junto con las [limitaciones](#limitaciones). Lo que sí sostiene es la
métrica: exige que la respuesta contenga el dato correcto, no solo que el
sistema conteste y cite.

---

## Cómo funciona

```
Pregunta
   │
   ▼
Se busca en la documentación indexada
   │  Búsqueda por significado: encuentra el fragmento
   │  aunque la pregunta use otras palabras
   ▼
¿Hay algo suficientemente relevante?
   │
   ├── No ──► "No tengo esa información"
   │           (sin consultar al modelo)
   │
   └── Sí ──► El modelo redacta la respuesta usando
              únicamente esos fragmentos, y cita cada uno
```

Los documentos se parten en fragmentos por sección, y **cada fragmento
conserva de qué documento y de qué sección salió**. Sin eso la cita sería
imposible de verificar, que es lo mismo que no citar.

---

## Decisiones de diseño

### Abstenerse antes de invocar al modelo

Si ningún fragmento supera el umbral de relevancia, el sistema responde que no
tiene la información **sin llamar al modelo**.

Dos beneficios de la misma decisión: se ahorra el costo de la llamada, y se
elimina la oportunidad de inventar. No hace falta pedirle a un modelo que no
alucine sobre un contexto vacío si directamente no se lo invoca.

### El corpus no se versiona

La documentación usada no se publica en este repositorio. Es material de
terceros, y documentación institucional real puede contener nombres de
profesionales, matrículas o datos de pacientes. Nada de eso hace falta para
demostrar que el sistema recupera y cita bien.

Lo que sí se publica es el origen de cada documento, en
[`corpus/README.md`](corpus/README.md).

### El umbral de abstención se midió, no se eligió a ojo

El filtro de relevancia necesita un valor de corte. En vez de estimarlo, se
midió: para las 42 preguntas se registró el puntaje del mejor fragmento
recuperado, y se comparó la distribución de las que el corpus puede responder
contra la de las que no.

No hay separación limpia entre las dos poblaciones. Pero sí existe un tramo en
el que subir el corte frena preguntas sin respuesta **sin costo**, y a partir
de cierto punto cada abstención adicional empieza a costar respuestas
legítimas. El valor se fijó dentro de ese tramo, con margen respecto del borde
observado.

El script que lo mide es [`src/calibrar.py`](src/calibrar.py) y el resultado
queda en [`resultados-calibracion.json`](resultados-calibracion.json).

---

## Qué encontró la evaluación

Tener un conjunto de pruebas automatizado no es un trámite: **encontró tres
defectos que ninguna prueba manual habría detectado.**

**Un fragmento invisible.** Ante *"¿en cuánto tiempo me entregan la historia
clínica?"*, el sistema se abstenía. El dato estaba en el corpus, pero el
fragmento que lo contenía decía *"la copia debe entregarse dentro de las 48
horas"* sin mencionar en ningún lado de qué copia hablaba. Al partir el
documento, ese pedazo había perdido su tema. La corrección fue incorporar el
encabezado al texto indexado.

**Una métrica demasiado rígida.** El sistema contestaba *"la documentación
indica que la atención es arancelada, pero no especifica el arancel de
ortodoncia"* — una negativa mejor que la esperada — y la evaluación la contaba
como invento, porque buscaba una frase textual.

**Una métrica demasiado indulgente.** Y el problema inverso: la evaluación
premiaba responder y citar, no acertar. Un modo de búsqueda llegó a contestar
sobre turnos de odontología ante una pregunta sobre segunda opinión médica,
citando una fuente real, y quedó registrado como correcto. Ahora cada pregunta
declara el dato que la respuesta debe contener.

### La comparación que cambió una decisión

El diseño original combinaba dos formas de buscar: una que entiende el
significado de la pregunta, y otra que busca las palabras exactas. Es el patrón
habitual en producción. Antes de darlo por bueno, se midió: el mismo conjunto
de evaluación, ejecutado con cada mecanismo por separado y con los dos juntos.

| | Solo significado | Combinados | Solo palabras |
|---|---|---|---|
| Acertó el dato pedido | **100%** | 96,8% | 93,5% |
| Se abstuvo cuando debía | 100% | 100% | 100% |

**Combinarlos no mejoró nada, y en un caso empeoró el resultado.** Ante la
pregunta *"¿puedo pedir que otro profesional revise mi caso?"*, la búsqueda por
palabras encontró la frase "los profesionales revisan el caso" en un documento
sobre turnos de odontología, sin ninguna relación con el tema. Al combinar los
dos rankings, esa coincidencia literal desplazó fuera del resultado al
fragmento correcto.

Así que el sistema usa **solo búsqueda por significado**, en contra del patrón
habitual y a favor de lo que midió.

Eso no contradice a la industria: en producción la combinación se usa junto a
un reordenador que descarta justamente esas coincidencias espurias. Sin esa
pieza —que requiere capa paga— combinar puede salir peor que no combinar. Con
un corpus mucho mayor y vocabulario técnico más denso, la decisión merecería
revisarse.

Detalle en [`resultados-comparacion.json`](resultados-comparacion.json).

---

## Limitaciones

Declaradas acá para que no haya que buscarlas.

- **El corpus es chico**: 60 fragmentos. Cada consulta recupera cerca del 8%
  del total, así que la búsqueda tiene menos trabajo del que tendría a escala
  real.
- **El filtro de relevancia solo alcanza a un cuarto de los casos.** Se midió
  el puntaje de las 42 preguntas y las dos poblaciones se superponen: 8 de las
  11 preguntas sin respuesta puntúan por encima de la peor pregunta que sí
  tiene respuesta. No existe un corte que las separe. El valor elegido frena 3
  de esas 11 sin perder ninguna respuesta legítima; las 8 restantes las tiene
  que frenar la instrucción dada al modelo.
- **Es de un solo turno.** No maneja repreguntas: *"¿y para chicos?"* después
  de una pregunta sobre ayuno no funciona.
- **No incluye reordenador semántico**, que es la pieza que en producción
  filtra las coincidencias espurias. Requiere capa paga de Azure AI Search.

---

## Uso

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # completar con los valores del portal de Azure
```

```bash
python src/verificar.py       # comprueba credenciales y despliegues
python src/indice.py          # crea el índice y carga el corpus
python src/consulta.py        # consola interactiva de preguntas
python src/evaluar.py         # ejecuta el conjunto de evaluación
python src/comparar.py        # compara los modos de recuperación
python src/calibrar.py        # mide el umbral de abstención
```

---

## Contenido

| Archivo | Contenido |
|---|---|
| `src/ingesta.py` | Lectura del corpus y segmentación con procedencia |
| `src/indice.py` | Creación del índice y carga de fragmentos |
| `src/consulta.py` | Recuperación, umbral de abstención y generación con cita |
| `src/evaluar.py` | Evaluación contra el conjunto de preguntas |
| `src/comparar.py` | Comparación entre modos de recuperación |
| `src/calibrar.py` | Medición del umbral de abstención |
| `src/verificar.py` | Diagnóstico de configuración |
| `src/config.py` | Configuración por variables de entorno |
| `evaluacion/preguntas.yaml` | Casos respondibles, no respondibles y fuera de alcance |
| `corpus/README.md` | Origen de los documentos y por qué no se versionan |
| `resultados-evaluacion.json` | Resultado de la evaluación, caso por caso |
| `resultados-comparacion.json` | Resultado de la comparación entre modos |
| `resultados-calibracion.json` | Puntajes medidos para calibrar el umbral |

---

## Alcance

Responde sobre **qué dice la documentación**: procedimientos, requisitos,
horarios, derechos. No da indicaciones médicas ni diagnósticos, y el prompt lo
impide explícitamente. Ante una pregunta que pide conducta clínica, señala qué
documento trata el tema y remite a consulta profesional.

## Estado

Proyecto propio, implementado y evaluado. No está desplegado como servicio.
