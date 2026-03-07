'!TITLE "TASK3"
PROGRAM TASK3
    MOTOR ON
    TAKE ARM
    WHILE 1
        IF (I4 < I5) THEN
            PRINTDBG I4, I5
            DRIVEA @P (1, JOINT(1, J[I4])), (2, JOINT(2, J[I4])), (3, JOINT(3, J[I4])), (4, JOINT(4, J[I4])), (5, JOINT(5, J[I4])), (6, JOINT(6, J[I4])), NEXT
            I4 = (I4 + 1)
        ELSEIF (I4 = I5) THEN
            IF (I4 = 100) THEN
                I4 = 0
                I5 = 0
            ENDIF
        ENDIF
        
    WEND
END