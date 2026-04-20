import sqlite3

def delete_commentary():
    conn = sqlite3.connect('k_enter_news.db')
    c = conn.cursor()
    
    keywords = [
        '%[논평]%', '%[사설]%', '%[칼럼]%', '%[기자수첩]%', 
        '%[데스크칼럼]%', '%[시론]%', '%[기고]%',
        '%column%', '%opinion%', '%editorial%', '%commentary%'
    ]
    
    all_ids = set()
    for kw in keywords:
        c.execute('SELECT id FROM raw_news WHERE title LIKE ? COLLATE NOCASE', (kw,))
        rows = c.fetchall()
        for r in rows:
            all_ids.add(r[0])
            
    if not all_ids:
        print("No commentary news found in database.")
        conn.close()
        return

    ids_tuple = tuple(all_ids)
    
    # Handle single element tuple vs multiple
    if len(ids_tuple) == 1:
        where_clause = f"= {ids_tuple[0]}"
    else:
        where_clause = f"IN {ids_tuple}"

    try:
        c.execute(f"DELETE FROM processed_news WHERE raw_news_id {where_clause}")
        c.execute(f"DELETE FROM raw_news WHERE id {where_clause}")
        conn.commit()
        print(f"Successfully deleted {len(all_ids)} commentary news records.")
        print(f"Deleted IDs: {sorted(list(all_ids))}")
    except Exception as e:
        print(f"Error during deletion: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    delete_commentary()
