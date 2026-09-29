import asyncio
from twscrape import API, gather

async def main():
    api = API()  # Uses default accounts.db
    # Add account with cookies
    ct0 = "33d2d6a03a4d25786d15841355e8d12e26a64a30938c0634682d6f2fa7a36ca12be7106f05ccb58abf26df5d7e49a85570e2aaf2ae9dca30a0001186241294a3d5b7a88cfff2482cf2bbbdb28023f667"
    auth_token = "627b310f25b01fef273fe12963c2c73a805d6ce0"
    
    # We can just construct a cookie string
    cookies = f"ct0={ct0}; auth_token={auth_token};"
    
    # Add account (it will skip if already exists)
    try:
        await api.pool.add_account("user", "pass", "email", "epass", cookies=cookies)
    except Exception as e:
        print("Add account error:", e)
        
    await api.pool.login_all()
    
    print("Fetching list tweets via search...")
    tweets = await gather(api.search("list:2078086710118715619 filter:media", limit=50))
    print(f"Got {len(tweets)} tweets!")
    
    c = 0
    for t in tweets:
        if t.media:
            c += 1
    print(f"Media tweets: {c}")

if __name__ == "__main__":
    asyncio.run(main())
