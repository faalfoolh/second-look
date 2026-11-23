import csv, ast, sys
rows = list(csv.DictReader(open(sys.argv[1])))
def codes(r): return ast.literal_eval(r["scp_codes"])
def pick(cond, n=5):
    out = [r for r in rows if cond(r)]
    for r in out[:n]:
        print(r["ecg_id"], r["sex"], r["age"], codes(r), r["infarction_stadium1"], r["infarction_stadium2"], r["filename_hr"])
    print("count", len(out)); print()
acute = lambda r: "Stadium I" in (r["infarction_stadium1"] + r["infarction_stadium2"]) and "III" not in r["infarction_stadium1"]
print("Female, 35-60, anterior MI, acute stadium:")
pick(lambda r: r["sex"]=="1" and r["age"] and 35<=float(r["age"])<=60 and any(c in codes(r) and codes(r)[c]>=50 for c in ("AMI","ASMI","ALMI")) and acute(r))
print("Female, any MI, acute stadium, 35-65:")
pick(lambda r: r["sex"]=="1" and r["age"] and 35<=float(r["age"])<=65 and any(k in codes(r) for k in ("AMI","ASMI","ALMI","IMI","ILMI","LMI")) and acute(r))
print("Female normal 40-55:")
pick(lambda r: r["sex"]=="1" and r["age"] and 40<=float(r["age"])<=55 and codes(r)=={"NORM":100.0, "SR":0.0}, 3)
print("Male normal 40-55:")
pick(lambda r: r["sex"]=="0" and r["age"] and 40<=float(r["age"])<=55 and codes(r)=={"NORM":100.0, "SR":0.0}, 3)
