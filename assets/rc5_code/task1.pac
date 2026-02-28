'!TITLE "TASK1"
PROGRAM TASK1
    DEFINT len_str, pos, li1
    DEFSTR ls1, l_str, r_str
    DEFDBL valStr
    IF (I1 = 1) AND (I5 < 100) THEN
        ls1 = S1
        IF (ls1 = "0,0,0,0,0,0") THEN
            J[I5] = (0,0,0,0,0,0)
            I5 = I5 + 1
            I1 = 0
            REM EXIT PROGRAM IMMEDIATELY TO SAVE PROCESSING TIME.
            END
        ENDIF
        REM ===========================================================
        len_str = LEN(ls1)
        li1 = STRPOS(ls1, ",")
        l_str = LEFT$(ls1, li1 - 1)
        r_str = RIGHT$(ls1, len_str - li1)
        pos = 1
        valStr = VAL(l_str) * 1.0 / 100
        IF (I5 > 0) THEN
            IF (ABS(valStr - JOINT(pos, J[I5-1])) > 10.0) THEN
                I1 = 0
                END
            ENDIF
        ENDIF
        LETJ pos, J[I5] = valStr
        pos = pos + 1
        DO WHILE li1 > 0
            len_str = LEN(r_str)
            li1 = STRPOS(r_str, ",")
            IF pos = 6 THEN
                valStr = VAL(r_str) * 1.0 / 100
                IF (I5 > 0) THEN
                    IF (ABS(valStr - JOINT(pos, J[I5 - 1])) > 10.0) THEN
                        pos = 1
                        I1 = 0
                        END
                    ENDIF
                ENDIF
                LETJ pos, J[I5] = valStr
                pos = 1
                I5 = (I5 + 1)
                I1 = 0
            ENDIF
            l_str = LEFT(r_str, li1 - 1)
            r_str = RIGHT$(r_str, len_str - li1)
            valStr = VAL(l_str) * 1.0 / 100
            IF (I5 > 0) THEN
                IF (ABS(valStr - JOINT(pos, J[I5 - 1])) > 10.0)
                    pos = 1
                    I1 = 0
                    END
                ENDIF
            ENDIF
            LETJ pos, J[I5] = valStr
            pos = pos + 1
        LOOP
        I1 = 0
    ENDIF
END

