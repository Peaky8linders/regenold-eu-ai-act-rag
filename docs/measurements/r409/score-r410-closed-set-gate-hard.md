  [ 13/37] ok  mt_v2:mt_v2_001                      29.0s refs= 5
  [ 14/37] ok  mt_v2:mt_v2_002                      25.5s refs= 5
  [ 15/37] ok  mt_v2:mt_v2_003                      22.1s refs= 4
  [ 16/37] ok  mt_v2:mt_v2_004                      62.1s refs= 5
  [ 17/37] ok  mt_v2:mt_v2_005                      53.4s refs= 5
  [ 18/37] ok  mt_v2:mt_v2_006                      31.5s refs= 5
  [ 19/37] ok  mt_v2:mt_v2_007                      29.4s refs= 5
  [ 20/37] ok  mt_v2:mt_v2_008                      39.9s refs= 5
  [ 21/37] ok  mt_v2:mt_v2_009                      25.5s refs= 5
  [ 22/37] ok  mt_v2:mt_v2_010                      26.1s refs= 5
  [ 23/37] ok  mt_v2:mt_v2_011                      35.6s refs= 2
  [ 24/37] ok  mt_v2:mt_v2_012                      34.2s refs= 4
  [ 25/37] ok  mt_v2:mt_v2_013                      32.7s refs= 5
  [ 26/37] ok  mt_v2:mt_v2_014                      23.7s refs= 4
  [ 27/37] ok  mt_v2:mt_v2_015                      34.7s refs= 4
  [ 28/37] ok  mt_v2:mt_v2_016                      42.2s refs= 5
  [ 29/37] ok  mt_v2:mt_v2_017                      35.0s refs= 3
  [ 30/37] ok  mt_v2:mt_v2_018                      18.1s refs= 5
  [ 31/37] ok  mt_v2:mt_v2_019                      24.0s refs= 3
  [ 32/37] ok  mt_v2:mt_v2_020                      17.0s refs= 3
  [ 33/37] ok  mt_v2:mt_v2_021                      32.7s refs= 7
  [ 34/37] ok  mt_v2:mt_v2_022                      26.0s refs= 5
  [ 35/37] ok  mt_v2:mt_v2_023                      28.2s refs= 5
  [ 36/37] ok  mt_v2:mt_v2_024                      45.6s refs= 5
  [ 37/37] ok  mt_v2:mt_v2_025                      30.3s refs= 5
  [ 13/37] ok  mt_v2:mt_v2_001                      22.0s refs= 5
  [ 14/37] ok  mt_v2:mt_v2_002                      27.7s refs= 5
  [ 15/37] ok  mt_v2:mt_v2_003                      17.4s refs= 3
  [ 16/37] ok  mt_v2:mt_v2_004                      82.3s refs= 5
  [ 17/37] ok  mt_v2:mt_v2_005                      52.8s refs= 5
  [ 18/37] ok  mt_v2:mt_v2_006                      35.2s refs= 5
  [ 19/37] ok  mt_v2:mt_v2_007                      35.9s refs= 5
  [ 20/37] ok  mt_v2:mt_v2_008                      45.1s refs= 5
  [ 21/37] ok  mt_v2:mt_v2_009                      23.9s refs= 5
  [ 22/37] ok  mt_v2:mt_v2_010                      38.0s refs= 7
  [ 23/37] ok  mt_v2:mt_v2_011                      38.8s refs= 3
  [ 24/37] ok  mt_v2:mt_v2_012                      28.2s refs= 4
  [ 25/37] ok  mt_v2:mt_v2_013                      29.3s refs= 5
  [ 26/37] ok  mt_v2:mt_v2_014                      30.6s refs= 1
  [ 27/37] ok  mt_v2:mt_v2_015                      23.5s refs= 3
  [ 28/37] ok  mt_v2:mt_v2_016                      42.7s refs= 5
  [ 29/37] ok  mt_v2:mt_v2_017                      29.3s refs= 2
  [ 30/37] ok  mt_v2:mt_v2_018                      17.7s refs= 5
  [ 31/37] ok  mt_v2:mt_v2_019                      22.8s refs= 5
  [ 32/37] ok  mt_v2:mt_v2_020                      18.1s refs= 4
  [ 33/37] ok  mt_v2:mt_v2_021                      29.0s refs= 7
  [ 34/37] ok  mt_v2:mt_v2_022                      31.2s refs= 5
  [ 35/37] ok  mt_v2:mt_v2_023                      25.9s refs= 5
  [ 36/37] ok  mt_v2:mt_v2_024                      46.8s refs= 5
  [ 37/37] ok  mt_v2:mt_v2_025                      27.8s refs= 5
=== r410-closed-set-hard — hard FULL-AGG (baseline n=37 err=0 | branch n=37 err=0) ===
  axis          baseline    branch     delta
  ref_loose       0.7883    0.7748   -0.0135  <-- GOLD LOSS (R142.1 failure mode)
  ref_strict      0.3816    0.3813   -0.0003
  ref_conc        0.1551    0.1645   +0.0094
  tone            1.0000    1.0000   +0.0000
  kw_recall       0.8333    0.7883   -0.0450
  pred:gold         2.91      2.95     +0.03
  gold_drop_hd        15        16        +1  <-- GOLD DROPPED (hard rule #8)
  lat p50 s         31.9      29.3      -2.6
  => est. Overall uplift from the 3 reference axes: -0.04 pp
  [lat p50 above is confounded when a shared engine cache warms the 2nd arm — not a product signal in A/B mode]
=== r410-closed-set-hard — hard PAIRED (n=37, scored OK in BOTH arms) ===
  axis          baseline    branch     delta
  ref_loose       0.7883    0.7748   -0.0135  <-- GOLD LOSS (R142.1 failure mode)
  ref_strict      0.3816    0.3813   -0.0003
  ref_conc        0.1551    0.1645   +0.0094
  tone            1.0000    1.0000   +0.0000
  kw_recall       0.8333    0.7883   -0.0450
  pred:gold         2.91      2.95     +0.03
  gold_drop_hd        15        16        +1  <-- GOLD DROPPED (hard rule #8)
  => est. Overall uplift (leverage-weighted 3 ref axes): -0.04 pp
=== HARD RULE #8 GATE — gold heads dropped (branch vs baseline) ===
  hard   n=37    baseline=15    branch=16    delta=+1   [paired]
  4 row(s) where the branch dropped a gold head the baseline kept:
    - mt_v2:mt_v2_004  (hard)
    - mt_v2:mt_v2_007  (hard)
    - mt_v2:mt_v2_015  (hard)
    - mt_v2:mt_v2_022  (hard)
  !! FAIL — HARD RULE #8: the branch arm dropped MORE gold heads than the
  !! baseline on split(s): hard  (total delta +1)
