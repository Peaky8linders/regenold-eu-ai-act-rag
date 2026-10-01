== transport degradation, counted in each arm's run log
  R460-OFF    degenerate= 5 (persisted  2)  bedrock_fallback= 2  stage1_deterministic= 1
  R460-FULL   degenerate=17 (persisted  8)  bedrock_fallback= 8  stage1_deterministic= 2
  R461-OFF    degenerate= 2 (persisted  1)  bedrock_fallback= 1  stage1_deterministic= 0
  R461-COUNT  degenerate= 2 (persisted  1)  bedrock_fallback= 1  stage1_deterministic= 1

== levels (score payload)
  R461-COUNT  ans_conc= 82.05 ref_conc= 64.31 overall= 86.47 answers=  820.2 refs/row= 2.51 latency= 13.8s
              LC ans_loose= 60.00 ans_strict= 56.76 (27 answers cut)
  R460-OFF    ans_conc= 82.32 ref_conc= 58.43 overall= 86.90 answers=  803.4 refs/row= 2.78 latency=  9.8s
              LC ans_loose= 55.56 ans_strict= 54.05 (27 answers cut)
  R461-OFF    ans_conc= 81.95 ref_conc= 56.62 overall= 85.08 answers=  813.5 refs/row= 2.84 latency= 13.2s
              LC ans_loose= 62.96 ans_strict= 56.76 (29 answers cut)
  R460-FULL   ans_conc= 77.84 ref_conc= 63.95 overall= 86.09 answers=  867.4 refs/row= 2.51 latency= 11.8s
              LC ans_loose= 42.96 ans_strict= 40.54 (28 answers cut)

== THE GATE  R461-COUNT vs R461-OFF
   [all rows]  n=37
   ans_correctness_loose       94.82 ->   94.82  delta=  +0.00  CI[  -8.11,  +8.11]  B>1 A>1
   ans_correctness_strict      91.89 ->   91.89  delta=  +0.00  CI[  -8.11,  +8.11]  B>1 A>1
   ans_conciseness             81.95 ->   82.05  delta=  +0.10  CI[  -2.71,  +3.18]  B>12 A>14
   ref_correctness_loose       95.71 ->   97.14  delta=  +1.43  CI[  -7.14, +10.00]  B>2 A>1
   ref_correctness_strict      83.33 ->   84.76  delta=  +1.43  CI[  +0.00,  +4.29]  B>1 A>0
   ref_conciseness         *   56.62 ->   64.31  delta=  +7.69  CI[  +1.41, +15.05]  B>10 A>2
   regulatory_tone             97.30 ->   97.30  delta=  +0.00  CI[  -8.11,  +8.11]  B>1 A>1
   resp_speed                  86.81 ->   86.19  delta=  -0.62  CI[  -2.52,  +1.45]  B>15 A>22
   answer_chars                 813.5 ->    820.2  delta=    +6.6  CI[  -32.4,  +41.9]  B_up=16/37
   refs                    *      2.8 ->      2.5  delta=    -0.3  CI[   -0.6,   -0.1]  B_up=2/37
   gold head dropped: A=2 B=1 new_in_B=['rg_037']

== THE GATE  R461-COUNT vs R461-OFF
   [same leg label]  n=36
   ans_correctness_loose       94.68 ->   97.45  delta=  +2.78  CI[  +0.00,  +8.33]  B>1 A>0
   ans_correctness_strict      91.67 ->   94.44  delta=  +2.78  CI[  +0.00,  +8.33]  B>1 A>0
   ans_conciseness             82.44 ->   82.83  delta=  +0.39  CI[  -2.47,  +3.41]  B>12 A>13
   ref_correctness_loose       95.59 ->  100.00  delta=  +4.41  CI[  +0.00, +11.76]  B>2 A>0
   ref_correctness_strict      85.78 ->   87.25  delta=  +1.47  CI[  +0.00,  +4.41]  B>1 A>0
   ref_conciseness         *   57.70 ->   65.78  delta=  +8.09  CI[  +1.91, +15.49]  B>10 A>1
   regulatory_tone             97.22 ->  100.00  delta=  +2.78  CI[  +0.00,  +8.33]  B>1 A>0
   resp_speed                  87.05 ->   86.86  delta=  -0.20  CI[  -1.92,  +1.72]  B>15 A>21
   answer_chars                 801.7 ->    802.0  delta=    +0.3  CI[  -35.8,  +33.7]  B_up=15/36
   refs                    *      2.8 ->      2.4  delta=    -0.4  CI[   -0.7,   -0.1]  B_up=1/36
   gold head dropped: A=2 B=0 new_in_B=[]

== THE GATE  R461-COUNT vs R461-OFF
   [PRIMARY both]  n=27
   ans_correctness_loose       92.90 ->   96.60  delta=  +3.70  CI[  +0.00, +11.11]  B>1 A>0
   ans_correctness_strict      88.89 ->   92.59  delta=  +3.70  CI[  +0.00, +11.11]  B>1 A>0
   ans_conciseness             79.38 ->   79.90  delta=  +0.52  CI[  -3.27,  +4.56]  B>12 A>13
   ref_correctness_loose       94.44 ->  100.00  delta=  +5.56  CI[  +0.00, +14.81]  B>2 A>0
   ref_correctness_strict      82.10 ->   83.95  delta=  +1.85  CI[  +0.00,  +5.56]  B>1 A>0
   ref_conciseness         *   56.91 ->   67.10  delta= +10.19  CI[  +2.41, +19.20]  B>10 A>1
   regulatory_tone             96.30 ->  100.00  delta=  +3.70  CI[  +0.00, +11.11]  B>1 A>0
   resp_speed                  83.61 ->   83.49  delta=  -0.12  CI[  -2.36,  +2.38]  B>12 A>15
   answer_chars                 851.1 ->    851.6  delta=    +0.4  CI[  -47.7,  +45.0]  B_up=15/27
   refs                    *      2.7 ->      2.2  delta=    -0.5  CI[   -0.9,   -0.2]  B_up=1/27
   gold head dropped: A=2 B=0 new_in_B=[]

== NOISE FLOOR  R461-OFF vs R460-OFF (byte-identical prompts)
   [all rows]  n=37
   ans_correctness_loose       95.72 ->   94.82  delta=  -0.90  CI[  -8.11,  +5.41]  B>1 A>1
   ans_correctness_strict      91.89 ->   91.89  delta=  +0.00  CI[  -8.11,  +8.11]  B>1 A>1
   ans_conciseness             82.32 ->   81.95  delta=  -0.37  CI[  -4.00,  +2.80]  B>11 A>14
   ref_correctness_loose      100.00 ->   95.71  delta=  -4.29  CI[ -11.43,  +0.00]  B>0 A>2
   ref_correctness_strict      84.76 ->   83.33  delta=  -1.43  CI[  -4.29,  +0.00]  B>0 A>1
   ref_conciseness             58.43 ->   56.62  delta=  -1.81  CI[  -7.86,  +3.57]  B>3 A>5
   regulatory_tone            100.00 ->   97.30  delta=  -2.70  CI[  -8.11,  +0.00]  B>0 A>1
   resp_speed              *   90.16 ->   86.81  delta=  -3.35  CI[  -4.59,  -2.07]  B>6 A>31
   answer_chars                 803.4 ->    813.5  delta=   +10.2  CI[  -30.8,  +53.1]  B_up=14/37
   refs                           2.8 ->      2.8  delta=    +0.1  CI[   -0.1,   +0.2]  B_up=5/37
   gold head dropped: A=0 B=2 new_in_B=['rg_061', 'rg_088']

== NOISE FLOOR  R461-OFF vs R460-OFF (byte-identical prompts)
   [same leg label]  n=36
   ans_correctness_loose       97.45 ->   94.68  delta=  -2.78  CI[  -8.33,  +0.00]  B>0 A>1
   ans_correctness_strict      94.44 ->   91.67  delta=  -2.78  CI[  -8.33,  +0.00]  B>0 A>1
   ans_conciseness             81.83 ->   82.58  delta=  +0.75  CI[  -1.84,  +3.53]  B>11 A>13
   ref_correctness_loose      100.00 ->   95.59  delta=  -4.41  CI[ -11.76,  +0.00]  B>0 A>2
   ref_correctness_strict      85.78 ->   84.31  delta=  -1.47  CI[  -4.41,  +0.00]  B>0 A>1
   ref_conciseness             57.21 ->   55.34  delta=  -1.86  CI[  -8.09,  +3.68]  B>3 A>5
   regulatory_tone            100.00 ->   97.22  delta=  -2.78  CI[  -8.33,  +0.00]  B>0 A>1
   resp_speed              *   90.79 ->   87.42  delta=  -3.37  CI[  -4.66,  -2.09]  B>6 A>30
   answer_chars                 816.3 ->    815.8  delta=    -0.5  CI[  -39.2,  +36.2]  B_up=13/36
   refs                           2.8 ->      2.9  delta=    +0.1  CI[   -0.1,   +0.2]  B_up=5/36
   gold head dropped: A=0 B=2 new_in_B=['rg_061', 'rg_088']

== NOISE FLOOR  R461-OFF vs R460-OFF (byte-identical prompts)
   [PRIMARY both]  n=27
   ans_correctness_loose       96.60 ->   92.90  delta=  -3.70  CI[ -11.11,  +0.00]  B>0 A>1
   ans_correctness_strict      92.59 ->   88.89  delta=  -3.70  CI[ -11.11,  +0.00]  B>0 A>1
   ans_conciseness             78.56 ->   79.56  delta=  +1.00  CI[  -2.56,  +4.64]  B>11 A>13
   ref_correctness_loose      100.00 ->   94.44  delta=  -5.56  CI[ -14.81,  +0.00]  B>0 A>2
   ref_correctness_strict      82.10 ->   80.25  delta=  -1.85  CI[  -5.56,  +0.00]  B>0 A>1
   ref_conciseness             56.30 ->   53.95  delta=  -2.35  CI[ -10.06,  +4.75]  B>3 A>5
   regulatory_tone            100.00 ->   96.30  delta=  -3.70  CI[ -11.11,  +0.00]  B>0 A>1
   resp_speed              *   88.33 ->   84.10  delta=  -4.23  CI[  -5.71,  -2.66]  B>2 A>25
   answer_chars                 870.6 ->    870.0  delta=    -0.7  CI[  -51.6,  +49.5]  B_up=13/27
   refs                           2.8 ->      2.9  delta=    +0.1  CI[   -0.2,   +0.3]  B_up=5/27
   gold head dropped: A=0 B=2 new_in_B=['rg_061', 'rg_088']

== R460 verdict recomputed  R460-FULL vs R460-OFF
   [all rows]  n=37
   ans_correctness_loose       95.72 ->   94.82  delta=  -0.90  CI[  -8.11,  +5.41]  B>1 A>1
   ans_correctness_strict      91.89 ->   91.89  delta=  +0.00  CI[  -8.11,  +8.11]  B>1 A>1
   ans_conciseness         *   82.32 ->   77.84  delta=  -4.49  CI[  -8.77,  -0.68]  B>8 A>17
   ref_correctness_loose      100.00 ->   97.14  delta=  -2.86  CI[  -8.57,  +0.00]  B>0 A>1
   ref_correctness_strict      84.76 ->   84.76  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_conciseness         *   58.43 ->   63.95  delta=  +5.52  CI[  +0.71, +11.90]  B>7 A>1
   regulatory_tone            100.00 ->   97.30  delta=  -2.70  CI[  -8.11,  +0.00]  B>0 A>1
   resp_speed              *   90.16 ->   88.21  delta=  -1.96  CI[  -3.58,  -0.44]  B>6 A>31
   answer_chars            *    803.4 ->    867.4  delta=   +64.0  CI[  +16.9, +114.6]  B_up=19/37
   refs                    *      2.8 ->      2.5  delta=    -0.3  CI[   -0.5,   -0.1]  B_up=1/37
   gold head dropped: A=0 B=1 new_in_B=['rg_037']

== R460 verdict recomputed  R460-FULL vs R460-OFF
   [same leg label]  n=35
   ans_correctness_loose       97.38 ->   97.38  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_correctness_strict      94.29 ->   94.29  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_conciseness             82.04 ->   78.96  delta=  -3.08  CI[  -6.47,  +0.04]  B>8 A>15
   ref_correctness_loose      100.00 ->  100.00  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_correctness_strict      88.38 ->   88.38  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_conciseness         *   58.18 ->   63.79  delta=  +5.61  CI[  +0.51, +12.42]  B>6 A>1
   regulatory_tone            100.00 ->  100.00  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   resp_speed              *   91.32 ->   89.20  delta=  -2.12  CI[  -3.72,  -0.74]  B>5 A>30
   answer_chars            *    809.2 ->    857.8  delta=   +48.6  CI[   +7.7,  +91.9]  B_up=17/35
   refs                    *      2.8 ->      2.5  delta=    -0.3  CI[   -0.5,   -0.0]  B_up=1/35
   gold head dropped: A=0 B=0 new_in_B=[]

== R460 verdict recomputed  R460-FULL vs R460-OFF
   [PRIMARY both]  n=26
   ans_correctness_loose       96.47 ->   96.47  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_correctness_strict      92.31 ->   92.31  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_conciseness             78.72 ->   74.57  delta=  -4.15  CI[  -8.60,  +0.13]  B>8 A>15
   ref_correctness_loose      100.00 ->  100.00  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_correctness_strict      85.26 ->   85.26  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_conciseness         *   57.50 ->   64.62  delta=  +7.12  CI[  +0.64, +15.71]  B>6 A>1
   regulatory_tone            100.00 ->  100.00  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   resp_speed              *   88.96 ->   86.04  delta=  -2.91  CI[  -4.95,  -1.10]  B>3 A>23
   answer_chars            *    863.1 ->    928.5  delta=   +65.5  CI[  +11.2, +120.2]  B_up=17/26
   refs                    *      2.7 ->      2.4  delta=    -0.3  CI[   -0.7,   -0.0]  B_up=1/26
   gold head dropped: A=0 B=0 new_in_B=[]

== count-only vs the full block  R461-COUNT vs R460-FULL
   [all rows]  n=37
   ans_correctness_loose       94.82 ->   94.82  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_correctness_strict      91.89 ->   91.89  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_conciseness         *   77.84 ->   82.05  delta=  +4.22  CI[  +0.99,  +7.56]  B>17 A>9
   ref_correctness_loose       97.14 ->   97.14  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_correctness_strict      84.76 ->   84.76  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_conciseness             63.95 ->   64.31  delta=  +0.36  CI[  -5.04,  +5.62]  B>6 A>3
   regulatory_tone             97.30 ->   97.30  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   resp_speed                  88.21 ->   86.19  delta=  -2.02  CI[  -4.09,  +0.13]  B>12 A>25
   answer_chars            *    867.4 ->    820.2  delta=   -47.2  CI[  -90.5,   -3.1]  B_up=10/37
   refs                           2.5 ->      2.5  delta=    +0.0  CI[   -0.2,   +0.3]  B_up=3/37
   gold head dropped: A=1 B=1 new_in_B=[]

== count-only vs the full block  R461-COUNT vs R460-FULL
   [same leg label]  n=36
   ans_correctness_loose       97.45 ->   97.45  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_correctness_strict      94.44 ->   94.44  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_conciseness         *   78.06 ->   82.83  delta=  +4.78  CI[  +1.76,  +8.01]  B>17 A>8
   ref_correctness_loose      100.00 ->  100.00  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_correctness_strict      87.25 ->   87.25  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_conciseness             64.85 ->   65.78  delta=  +0.93  CI[  -4.51,  +6.27]  B>6 A>2
   regulatory_tone            100.00 ->  100.00  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   resp_speed                  88.84 ->   86.86  delta=  -1.99  CI[  -4.13,  +0.23]  B>12 A>24
   answer_chars            *    859.9 ->    802.0  delta=   -57.9  CI[  -97.5,  -19.6]  B_up=9/36
   refs                           2.5 ->      2.4  delta=    -0.1  CI[   -0.3,   +0.0]  B_up=2/36
   gold head dropped: A=0 B=0 new_in_B=[]

== count-only vs the full block  R461-COUNT vs R460-FULL
   [PRIMARY both]  n=27
   ans_correctness_loose       96.60 ->   96.60  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_correctness_strict      92.59 ->   92.59  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ans_conciseness         *   73.53 ->   79.90  delta=  +6.37  CI[  +2.42, +10.44]  B>17 A>8
   ref_correctness_loose      100.00 ->  100.00  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_correctness_strict      83.95 ->   83.95  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   ref_conciseness             65.93 ->   67.10  delta=  +1.17  CI[  -6.17,  +7.84]  B>6 A>2
   regulatory_tone            100.00 ->  100.00  delta=  +0.00  CI[  +0.00,  +0.00]  B>0 A>0
   resp_speed                  85.69 ->   83.49  delta=  -2.20  CI[  -5.01,  +0.72]  B>8 A>19
   answer_chars            *    928.7 ->    851.6  delta=   -77.1  CI[ -127.1,  -25.9]  B_up=9/27
   refs                           2.3 ->      2.2  delta=    -0.1  CI[   -0.3,   +0.0]  B_up=2/27
   gold head dropped: A=0 B=0 new_in_B=[]
