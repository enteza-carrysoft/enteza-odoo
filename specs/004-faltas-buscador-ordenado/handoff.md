# Handoff — 004-faltas-buscador-ordenado

**Summary:** rental_custom 19.0.1.17.0 implementado (orden por referencia, columna Referencia, sin paginación, buscador, flechas, «Solo con faltas»); estático en verde; sin comitear ni desplegar; AC1–AC10 pendientes de pantalla.
**Final phase:** VERIFY · **Verdict:** none · **Mode:** create
**Generated:** 2026-10-08T18:16:59.367Z

> ⚠️ This run is NOT verified (phase VERIFY). Do not present it as done.

## Acceptance criteria
| AC | Status |
|----|--------|
| AC1 | pending |
| AC2 | pending |
| AC3 | pending |
| AC4 | pending |
| AC5 | pending |
| AC6 | pending |
| AC7 | pending |
| AC8 | pending |
| AC9 | pending |
| AC10 | pending |
| AC11 | pass |

## Approvals
- READ_SPEC: mcp-elicitation at 2026-10-08T18:11:16.215Z
- ARCHITECTURE: mcp-elicitation at 2026-10-08T18:13:28.714Z

## Decisions, blockers and diagnoses
- **evidence** (2026-10-08T18:16:53.893Z): 2026-10-08 estático: odoo_validate 0 ERROR (6 WARN previos en rental_loss_report_views.xml); validar_vistas.py sin fallos de esquema; validar_modulo.py «todo el código se carga»; py_compile, node --check (ESM) y parseo XML OK; simular_herencia_owl: xpath //ListRenderer 1 coincidencia, raíz única. Bundle web.assets_web.min.js de enteza contiene onCellKeydownEditMode, getRowClass, get rendererProps,
- **decision** (2026-10-08T18:16:54.180Z): Intro con buscador vacío y «Solo con faltas» activo salta a la siguiente fila visible (no a la nativa, que puede estar oculta). Orden fijado en el servidor al crear las líneas (missing_line_sort_key), no con default_order.

## Checkpoints (rollback targets)
- cp-muzuuknm (active)

## Data journal
| Checkpoint | # | Op | Model | Status | Ids |
|---|---|---|---|---|---|
| - | - | - | - | - | - |

## Configuration in effect
autonomy=supervised · requireSpecForChanges=true · requireCheckpointBeforeMutation=true · securityReviewRequired=true · documentationPolicy=required · executeAllowlist=[]

## Next steps
- Commit y push (el usuario confirma cada uno por separado)
- invoke git-aggregate en el servidor → Actualizar lista → Actualizar rental_custom; comprobar latest_version = 19.0.1.17.0 por RPC
- Ctrl+F5 y probar en pantalla con un alquiler de más de 40 líneas, pulsando Cancelar sin facturar (AC2–AC10)
- Revisión de seguridad (odoo-security-reviewer) y odoo-qa con la evidencia de pantalla; luego sdd_phase succeed o fail
- Spec 003 sigue en VERIFY con AC1 pendiente

Commits are never automatic: review and commit following the project's rules.
