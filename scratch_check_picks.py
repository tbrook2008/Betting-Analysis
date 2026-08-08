import datetime
from analysis.teacher import Teacher

picks = [
    "Max Clark", "Steven Kwan", "Yordan Alvarez", "Ty France", "Cole Carrigg",
    "Jeremy Pena", "James McCann", "Jackson Merrill", "Shohei Ohtani",
    "Freddie Freeman", "Ceddanne Rafaela", "Jake Bauers"
]

teacher = Teacher()
dt = datetime.date(2026, 8, 4)

results = []
for p in picks:
    res = teacher._get_result(p, dt, "hits")
    if res is not None:
        if res > 0.5:
            results.append(f"✅ {p}: {res} hits (WIN)")
        else:
            results.append(f"❌ {p}: {res} hits (LOSS)")
    else:
        results.append(f"❓ {p}: No data / DNP")

for r in results:
    print(r)
