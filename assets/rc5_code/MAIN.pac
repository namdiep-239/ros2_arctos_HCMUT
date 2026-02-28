'!TITLE "MAIN"
PROGRAM MAIN
    DEFIN li1
    REM Head of Queue
    I1 = 0
    REM Tail of Queue
    I2 = 0
    REM LENGTH of Queue
    I3 = 0
    I4 = 0
    I5 = 0
    FLUSH #1
    FOR li1 = 0 to 99
        J[li1] = (0,0,0,0,0,0)
    NEXT li1
    REM ==== Read Serial Task
    RUN TASK0, C = 10
    DELAY 20
    REM ==== Process recevied data
    RUN TASK1, C = 20
    REM ==== RUN ROBOT
    RUN TASK3, C = 50
    REM ==== Transmit current joint
    RUN GET_JOINT, C = 100
END