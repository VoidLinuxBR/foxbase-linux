* Exemplo FoxBASE+/Harbour: lista clientes ativos
PROCEDURE Main
   CLS
   USE clientes
   ? "Clientes ativos"
   ? REPLICATE("-", 40)
   DO WHILE .NOT. EOF()
      IF ativo
         ? codigo, nome, limite
      ENDIF
      SKIP
   ENDDO
   USE
   ?
   WAIT
RETURN
