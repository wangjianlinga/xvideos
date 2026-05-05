import sqlite3
conn = sqlite3.connect(r'e:\code\github\xvideos\data\videos.db')
cursor = conn.cursor()
cursor.execute("UPDATE videos SET url = '123213'")
conn.commit()
cursor.execute("SELECT url FROM videos")
rows = cursor.fetchall()
print(f"Updated rows: {len(rows)}")
for r in rows:
    print(r[0])
conn.close()
