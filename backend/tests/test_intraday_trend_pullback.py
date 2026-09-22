from app.research.intraday_trend_pullback import evaluate

def test_intraday_evaluator_uses_next_bar_entry_and_stop_first():
    bars=[{"timestamp":str(i),"open":100,"high":101,"low":99,"close":100,"volume":1} for i in range(20)]
    bars[19]={"timestamp":"19","open":100,"high":101,"low":99,"close":100.6,"volume":1}
    bars.append({"timestamp":"20","open":100.7,"high":102.5,"low":99.8,"close":101,"volume":1})
    bars.append({"timestamp":"21","open":101,"high":103,"low":99,"close":101,"volume":1})
    trades=evaluate({"SPY":bars})
    assert trades[0].entry_timestamp=="20"
    assert trades[0].exit_reason=="stop"
