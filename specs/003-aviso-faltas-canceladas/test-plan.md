# Test plan

Prueba escrita y **no ejecutada** (sin `--test-enable`). Tras desplegar: comprobación por RPC
y en pantalla con el alquiler 41255027.

| AC | Scenario | Layer (static/server/rpc/ui/tests/manual) | Status |
|----|----------|--------------------------------------------|--------|
| AC1 | `test_faltas_desde_pedido.test_aviso_ignora_faltas_canceladas` + RPC sobre 41255027 (`compensation_order_ids` vacío) | tests + rpc | pending |
| AC2 | Pruebas existentes sin modificar; validadores en verde | static | pass |
