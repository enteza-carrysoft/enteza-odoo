# Handoff — 002-faltas-desde-pedido

**Summary:** rental_custom 19.0.1.16.0 (Registrar faltas desde el pedido) escrita y validada por sintaxis; pruebas escritas y NO ejecutadas; sin comitear ni desplegar.
**Final phase:** VERIFY · **Verdict:** none · **Mode:** create
**Generated:** 2026-10-07T17:28:29.682Z

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
| AC10 | pass |

## Approvals
- READ_SPEC: mcp-elicitation at 2026-10-07T17:17:55.631Z
- ARCHITECTURE: mcp-elicitation at 2026-10-07T17:25:30.363Z

## Decisions, blockers and diagnoses
- none

## Checkpoints (rollback targets)
- cp-muydp1a8 (active)

## Data journal
| Checkpoint | # | Op | Model | Status | Ids |
|---|---|---|---|---|---|
| - | - | - | - | - | - |

## Configuration in effect
autonomy=supervised · requireSpecForChanges=true · requireCheckpointBeforeMutation=true · securityReviewRequired=true · documentationPolicy=required · executeAllowlist=[]

## Next steps
- Commit y push con confirmación del usuario
- invoke git-aggregate, actualizar rental_custom y comprobar latest_version = 19.0.1.16.0 por RPC
- Prueba real con el usuario: un pedido sin albaranes, registrar faltas, confirmar el pedido de faltas y comprobar baja y estado Devuelto
- Solo después: desactivar 'Traslado de alquiler' y cancelar los albaranes pasados (entregas y recogidas)
- Pendiente aparte: SEV/IN/01311 sigue abierta; plantilla rental_availability_popup_template.xml mal formada (preexistente, no cargada)

Commits are never automatic: review and commit following the project's rules.
