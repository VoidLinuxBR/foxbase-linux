/*
 * bridge.prg - ponte do foxbase-linux com o Harbour
 *
 * Executado pelo hbrun (ou compilado com hbmk2), fica esperando comandos
 * numa FIFO e executa cada linha como o hbrun faz no prompt: o texto vira o
 * corpo de um codeblock compilado em tempo de execução (hb_compileFromBuf),
 * então qualquer comando ou função do Harbour funciona: ALERT(), ACHOICE(),
 * MEMOEDIT(), @...SAY/GET, hb_*() etc.
 *
 * Protocolo (uma linha por item, terminando em "END"):
 *   pedido : CP <codepage> | DBF <arquivo> | REC <n> <eof> | DATE <fmt> |
 *            CENT <ON|OFF> | DEC <n> | VAR <nome> <tipo> <valor> | CLS |
 *            SCR <linha> <texto> | POS <linha> <coluna> | OUT <arquivo> |
 *            CMD <comando>
 *   resposta: ERR <mensagem> | DBF <arquivo> | REC <n> <eof> | VAR ... |
 *            SCR <linha> <texto> | POS <linha> <coluna> | END
 *
 * Copyright (c) 2026, Vilmar Catafesta <vcatafesta@gmail.com>
 * Licença: MIT
 */

#include "hbmemvar.ch"

REQUEST HB_CODEPAGE_PT850
REQUEST HB_CODEPAGE_PTISO
REQUEST HB_CODEPAGE_UTF8EX
REQUEST DBFCDX, DBFNTX, DBFFPT

PROCEDURE Main( cIn, cOut )

   LOCAL hIn, hOut, cLine, cKey, cArg, cAlt, cCmd, cDbf
   LOCAL nRec, lEof, cBuf := "", nPos, n, cScreenBefore

   hb_cdpSelect( "PT850" )
   hb_SetTermCP( "UTF8EX" )
   SET SCOREBOARD OFF
   SET CONFIRM OFF
   SET DELETED OFF
   SET EXACT OFF
   SET TALK OFF

   hIn := FOpen( cIn, 0 )
   hOut := FOpen( cOut, 1 )
   IF hIn < 0 .OR. hOut < 0
      QUIT
   ENDIF

   DO WHILE .T.
      cAlt := ""
      cCmd := NIL
      cDbf := NIL
      nRec := 0
      lEof := .F.
      DO WHILE .T.
         cLine := ReadLine( hIn, @cBuf )
         IF cLine == NIL
            QUIT
         ENDIF
         nPos := At( " ", cLine + " " )
         cKey := Left( cLine, nPos - 1 )
         cArg := SubStr( cLine, nPos + 1 )
         DO CASE
         CASE cKey == "END"
            EXIT
         CASE cKey == "QUIT"
            QUIT
         CASE cKey == "CP"
            hb_cdpSelect( cArg )
         CASE cKey == "DBF"
            cDbf := cArg
         CASE cKey == "REC"
            nRec := Val( hb_TokenGet( cArg, 1 ) )
            lEof := hb_TokenGet( cArg, 2 ) == "1"
         CASE cKey == "DATE"
            Set( _SET_DATEFORMAT, cArg )
         CASE cKey == "DEC"
            Set( _SET_DECIMALS, Val( cArg ) )
         CASE cKey == "VAR"
            SetVar( cArg )
         CASE cKey == "CLS"
            CLS
         CASE cKey == "SCR"
            n := Val( hb_TokenGet( cArg, 1 ) )
            DispOutAt( n, 0, PadR( SubStr( cArg, At( " ", cArg ) + 1 ), MaxCol() + 1 ) )
         CASE cKey == "POS"
            SetPos( Val( hb_TokenGet( cArg, 1 ) ), Val( hb_TokenGet( cArg, 2 ) ) )
         CASE cKey == "OUT"
            cAlt := cArg
         CASE cKey == "CMD"
            cCmd := cArg
         ENDCASE
      ENDDO

      /* banco atual do foxbase-linux */
      IF cDbf != NIL
         IF Empty( cDbf )
            dbCloseAll()
         ELSEIF Empty( Alias() ) .OR. !( Upper( dbInfo( 10 ) ) == Upper( cDbf ) )
            dbCloseAll()
            BEGIN SEQUENCE WITH {| e | Break( e ) }
               dbUseArea( .T., "DBFNTX", cDbf, NIL, .F., .F. )
            END SEQUENCE
         ENDIF
      ENDIF
      IF ! Empty( Alias() )
         dbGoto( iif( lEof, LastRec() + 1, nRec ) )
      ENDIF

      cScreenBefore := ScreenText()
      IF ! Empty( cAlt )
         SET ALTERNATE TO ( cAlt )
         SET ALTERNATE ON
         SET CONSOLE OFF
      ENDIF

      Exec( cCmd, hOut )

      SET CONSOLE ON
      SET ALTERNATE OFF
      SET ALTERNATE TO

      /* devolve o estado */
      IF Empty( Alias() )
         FWrite( hOut, "DBF " + hb_eol() )
      ELSE
         dbCommit()
         FWrite( hOut, "DBF " + dbInfo( 10 ) + hb_eol() )
         FWrite( hOut, "REC " + hb_ntos( RecNo() ) + " " + iif( Eof(), "1", "0" ) + hb_eol() )
      ENDIF
      SendVars( hOut )
      IF !( ScreenText() == cScreenBefore )
         FOR n := 0 TO MaxRow()
            FWrite( hOut, "SCR " + hb_ntos( n ) + " " + RTrim( ScreenRow( n ) ) + hb_eol() )
         NEXT
         FWrite( hOut, "POS " + hb_ntos( Row() ) + " " + hb_ntos( Col() ) + hb_eol() )
      ENDIF
      FWrite( hOut, "END" + hb_eol() )
   ENDDO

   RETURN

STATIC PROCEDURE Exec( cCommand, hOut )

   LOCAL cFunc, cHRB, pHRB, bBlock, oErr

   IF Empty( cCommand )
      RETURN
   ENDIF
   cFunc := ;
      "STATIC FUNCTION __FOXDOT()" + hb_eol() + ;
      "RETURN {||" + hb_eol() + ;
      "   " + cCommand + hb_eol() + ;
      "   RETURN NIL" + hb_eol() + ;
      "}" + hb_eol()

   BEGIN SEQUENCE WITH {| e | Break( e ) }
      cHRB := hb_compileFromBuf( cFunc, "hbrun", "-n2", "-q2" )
      IF Empty( cHRB )
         FWrite( hOut, "ERR Syntax error." + hb_eol() )
      ELSE
         pHRB := hb_hrbLoad( cHRB )
         IF ! Empty( pHRB )
            bBlock := hb_hrbDo( pHRB )
            Eval( bBlock )
         ENDIF
      ENDIF
   RECOVER USING oErr
      IF ValType( oErr ) == "O"
         FWrite( hOut, "ERR " + ErrText( oErr ) + hb_eol() )
      ENDIF
   END SEQUENCE

   RETURN

STATIC FUNCTION ErrText( oErr )

   LOCAL cText := oErr:description

   IF ! Empty( oErr:operation )
      cText += ": " + oErr:operation
   ENDIF

   RETURN cText

STATIC PROCEDURE SetVar( cArg )

   LOCAL cName := hb_TokenGet( cArg, 1 )
   LOCAL cType := hb_TokenGet( cArg, 2 )
   LOCAL cValue := SubStr( cArg, Len( cName ) + Len( cType ) + 3 )
   LOCAL xValue

   DO CASE
   CASE cType == "N"
      xValue := Val( cValue )
   CASE cType == "D"
      xValue := hb_SToD( cValue )
   CASE cType == "L"
      xValue := cValue == "T"
   CASE cType == "U"
      IF ! __mvExist( cName )
         __mvPublic( cName )
      ENDIF
      RETURN
   OTHERWISE
      xValue := hb_StrReplace( cValue, { "\n" => Chr( 10 ), "\\" => "\" } )
   ENDCASE
   IF __mvExist( cName )
      __mvPut( cName, xValue )
   ELSE
      __mvPublic( cName )
      __mvPut( cName, xValue )
   ENDIF

   RETURN

STATIC PROCEDURE SendVars( hOut )

   LOCAL nCount := __mvDbgInfo( HB_MV_PUBLIC )
   LOCAL n, cName, xValue, cValue, cType

   FOR n := 1 TO nCount
      xValue := __mvDbgInfo( HB_MV_PUBLIC, n, @cName )
      cType := ValType( xValue )
      DO CASE
      CASE cType == "N"
         cValue := hb_ntos( xValue )
      CASE cType == "D"
         cValue := DToS( xValue )
      CASE cType == "L"
         cValue := iif( xValue, "T", "F" )
      CASE cType == "C" .OR. cType == "M"
         cType := "C"
         cValue := hb_StrReplace( xValue, { "\" => "\\", Chr( 10 ) => "\n", Chr( 13 ) => "" } )
      OTHERWISE
         LOOP
      ENDCASE
      IF Left( cName, 2 ) == "__" .OR. Upper( cName ) == "GETLIST"
         LOOP
      ENDIF
      FWrite( hOut, "VAR " + cName + " " + cType + " " + cValue + hb_eol() )
   NEXT

   RETURN

STATIC FUNCTION ScreenText()

   LOCAL cText := "", n

   FOR n := 0 TO MaxRow()
      cText += ScreenRow( n )
   NEXT

   RETURN cText

STATIC FUNCTION ScreenRow( n )

   LOCAL cBuf := SaveScreen( n, 0, n, MaxCol() )
   LOCAL nCells := MaxCol() + 1
   LOCAL nSize := Int( hb_BLen( cBuf ) / nCells )
   LOCAL cRow := "", i

   FOR i := 0 TO nCells - 1
      IF nSize >= 4   /* célula unicode: caractere UTF-16LE + cor + atributo */
         cRow += hb_UChar( Bin2W( hb_BSubStr( cBuf, i * 4 + 1, 2 ) ) )
      ELSE            /* célula VGA: caractere + cor */
         cRow += hb_BSubStr( cBuf, i * 2 + 1, 1 )
      ENDIF
   NEXT

   RETURN cRow

STATIC FUNCTION ReadLine( hIn, cBuf )

   LOCAL nPos, cChunk := Space( 4096 ), nRead

   DO WHILE ( nPos := At( Chr( 10 ), cBuf ) ) == 0
      nRead := FRead( hIn, @cChunk, 4096 )
      IF nRead <= 0
         RETURN NIL
      ENDIF
      cBuf += Left( cChunk, nRead )
   ENDDO
   cChunk := Left( cBuf, nPos - 1 )
   cBuf := SubStr( cBuf, nPos + 1 )

   RETURN cChunk
