# Handoff — 001-prestamo-reserva-acotada

**Summary:** 19.0.10.1.0 escrita y validada por sintaxis (AC9, AC10 pass); AC1-AC8 con pruebas escritas y NO ejecutadas; sin desplegar ni comitear.
**Final phase:** VERIFY · **Verdict:** none · **Mode:** bug
**Generated:** 2026-10-07T16:11:33.106Z

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
| AC9 | pass |
| AC10 | pass |

## Approvals
- READ_SPEC: mcp-elicitation at 2026-10-07T16:06:59.827Z

## Decisions, blockers and diagnoses
- **evidence** (2026-10-07T16:11:24.918Z): 2026-10-07: odoo_validate 0/0, validar_modulo.py 'Todo el código se carga', validar_vistas.py 'Sin fallos de esquema', py_compile OK, sin diff en security/ ni views/. Pruebas Odoo escritas (AC1-AC8) y NO ejecutadas: no hay --test-enable ni instancia de pruebas; enteza es producción. AC1/AC3 se verificarán por RPC tras desplegar (pedido 2648: enteza_falta <= product_uom_qty en todas las líneas). He

## Checkpoints (rollback targets)
- cp-muyaw2mp (active)

## Data journal
| Checkpoint | # | Op | Model | Status | Ids |
|---|---|---|---|---|---|
| - | - | - | - | - | - |

## Configuration in effect
autonomy=supervised · requireSpecForChanges=true · requireCheckpointBeforeMutation=true · securityReviewRequired=true · documentationPolicy=required · executeAllowlist=[]

## Next steps
- Commit (con confirmación del usuario) y push, por separado
- invoke git-aggregate en el servidor, Actualizar lista, actualizar el módulo; comprobar latest_version = 19.0.10.1.0 por RPC
- RPC sobre pedido 2648: enteza_falta <= product_uom_qty en todas las líneas (AC1)
- Revisar préstamos reserved/approved existentes por si tienen cantidades infladas (el usuario API no tiene el grupo de préstamos: lo hace admin)
- Probar en la interfaz cancelar un préstamo aprobado y una entrega parcial cuando haya un caso real
- Marcar ACs según evidencia y cerrar con sdd_phase succeed solo si todo está en pass

Commits are never automatic: review and commit following the project's rules.
