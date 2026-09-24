# 🎯 New Features UI Guide

## Where to Find Your New Features

### 1. **Carbon Credits & Leaderboard** 🏆

**Location:** Click the **"Leaderboard"** tab at the top

**What You'll See:**
- 🏆 **Top 3 Podium** - Top performers with their credit totals
- 📊 **Full Leaderboard Table** - All suppliers ranked by credits
- 🎖️ **Badge Glossary** - Explanation of all badges

**How to Test:**
1. Submit 2-3 audits with different suppliers
2. Click "Leaderboard" tab
3. See suppliers ranked by credits earned
4. Check badges awarded (Green Champion, Eco Performer, etc.)

---

### 2. **Carbon Token Management** 💰

**Location:** Click the **"Carbon Tokens"** tab at the top

**What You'll See:**
- 💰 **Token Overview** - Asset ID, balance, supply stats
- 🔧 **Token Management** - 6 action cards:
  - ✅ Opt-In to Receive Tokens
  - 🏭 Create Token
  - 📤 Issue Credits
  - 🔥 Retire Credits
  - 🎨 Create Audit NFT
  - 🔍 Check Balance
- 📜 **Transaction History** - Issued/Received/Retired/NFTs tabs

**How to Test:**
1. Click "Carbon Tokens" tab
2. Create a token (if not created yet)
3. Issue credits to an address
4. View transaction history

---

### 3. **Automatic Credit Scoring** ⚡

**Location:** Happens automatically after every audit

**What Happens:**
1. Submit an audit on the Dashboard
2. After completion, check the **Latest Result** panel
3. Scroll down to see **"CARBON CREDITS AWARDED"** section
4. Shows:
   - Base Credits earned
   - Streak Bonus (if applicable)
   - Improvement Bonus (if applicable)
   - Total Credits
   - New Balance
   - Badges earned

**Credit Thresholds:**
- **0.00-0.20**: 100 credits + "Green Champion" 🌿
- **0.21-0.40**: 60 credits + "Eco Performer" 🌱
- **0.41-0.60**: 20 credits + "In Progress" 🔄
- **> 0.60**: 0 credits

**Bonuses:**
- **Streak Bonus**: +50 credits for 3 consecutive audits below 0.40
- **Improvement Bonus**: +30 credits if score improves by >0.15

---

### 4. **Compliance Bonds** 🔒

**Location:** Automatic enforcement in audit results

**What Happens:**
- **HIGH risk (0.60-0.80)**: Locks 50 CCC as compliance bond
- **Improved (<0.60)**: Releases bond back to supplier
- **Critical (≥0.80)**: Burns bond permanently

**How to See:**
- Submit audits with different risk scores
- Check audit result for bond status
- API: `GET /api/bonds/{supplier_id}`

---

### 5. **Marketplace & Staking** 🏪

**Location:** API endpoints (UI coming soon)

**Marketplace:**
- `POST /api/marketplace/list` - List credits for sale
- `POST /api/marketplace/buy` - Purchase credits
- `GET /api/marketplace/listings` - View all listings

**Staking:**
- `POST /api/staking/stake` - Lock credits for 30 days
- `POST /api/staking/unstake` - Retrieve after lock period
- `POST /api/staking/claim-yield` - Claim 10% ALGO yield
- `GET /api/staking/{supplier_id}` - Check stake status

---

## 🚀 Quick Test Workflow

### Test 1: See Credits in Action
```bash
1. Go to Dashboard tab
2. Submit audit with:
   - Supplier: "GreenTech Industries"
   - Emissions: 1500
   - Violations: 1
   - Sector: General Industry
3. Wait for completion
4. Scroll down in "Latest Result" to see credits awarded
5. Click "Leaderboard" tab to see supplier ranked
```

### Test 2: Test Streak Bonus
```bash
1. Submit 3 audits for same supplier with low scores:
   - Audit 1: Emissions 1000, Violations 0 (score ~0.15)
   - Audit 2: Emissions 1200, Violations 1 (score ~0.20)
   - Audit 3: Emissions 1100, Violations 0 (score ~0.18)
2. On 3rd audit, you'll get +50 streak bonus!
3. Check Leaderboard to see "Consistency Streak" badge
```

### Test 3: Test Improvement Bonus
```bash
1. Submit audit with high score:
   - Emissions: 5000, Violations: 10 (score ~0.70)
2. Submit 2nd audit for same supplier with improved score:
   - Emissions: 2000, Violations: 2 (score ~0.35)
3. Improvement = 0.70 - 0.35 = 0.35 (>0.15)
4. You'll get +30 improvement bonus!
5. Check for "Improver" badge in Leaderboard
```

### Test 4: Explore Carbon Tokens
```bash
1. Click "Carbon Tokens" tab
2. Scroll through Token Overview (shows stats)
3. Scroll to Token Management section
4. Try "Create Token" if you have wallet connected
5. Check Transaction History tabs at bottom
```

---

## 🔍 Troubleshooting

### "I don't see the Leaderboard tab"
- Make sure you're on the main dashboard (http://localhost:8001)
- Look for tabs: Dashboard | **Leaderboard** | Carbon Tokens | Live Simulator

### "Leaderboard is empty"
- Submit at least 1 audit first
- Credits are calculated automatically after each audit
- Refresh the page and click Leaderboard tab again

### "I don't see credits in audit results"
- Scroll down in the "Latest Result" panel
- Look for section titled "CARBON CREDITS AWARDED"
- If not visible, check browser console for errors (F12)

### "Carbon Tokens tab shows 'Not Created'"
- This is normal - token needs to be created first
- Click "Create Token" button in Token Management section
- Requires wallet connection (optional for testing)

---

## 📊 API Endpoints for Testing

### Credits
```bash
# Get supplier credits
GET http://localhost:8001/api/credits/{supplier_id}

# Get credit history with charts
GET http://localhost:8001/api/credits/{supplier_id}/history

# Get leaderboard
GET http://localhost:8001/api/leaderboard
```

### Bonds
```bash
# Get bond status
GET http://localhost:8001/api/bonds/{supplier_id}

# List all bonds
GET http://localhost:8001/api/bonds
```

### Marketplace
```bash
# View listings
GET http://localhost:8001/api/marketplace/listings

# Create listing
POST http://localhost:8001/api/marketplace/list
```

### Staking
```bash
# Check stake status
GET http://localhost:8001/api/staking/{supplier_id}
```

---

## 💡 Pro Tips

1. **Use different supplier names** to see multiple entries in leaderboard
2. **Submit multiple audits** for same supplier to trigger streak/improvement bonuses
3. **Vary emissions and violations** to see different credit amounts
4. **Check the "Latest Result" panel** after each audit for credit details
5. **Leaderboard updates automatically** after each audit

---

## 🎯 Expected Behavior

After submitting an audit, you should see:

1. ✅ Audit completes successfully
2. ✅ "Latest Result" shows risk score and classification
3. ✅ Scroll down to see "CARBON CREDITS AWARDED" section
4. ✅ Credits, badges, and bonuses displayed
5. ✅ Click "Leaderboard" tab to see supplier ranked
6. ✅ Supplier appears with total credits and badges

---

## 🆘 Still Can't See Features?

1. **Clear browser cache** (Ctrl+Shift+Delete)
2. **Hard refresh** (Ctrl+F5)
3. **Check browser console** (F12) for JavaScript errors
4. **Restart the server**:
   ```bash
   # Stop server (Ctrl+C)
   # Restart
   uvicorn webapp:app --reload --port 8001
   ```
5. **Check if files are up to date**:
   - `webapp.py` should have credit endpoints
   - `web/index.html` should have Leaderboard tab
   - `web/static/app.js` should have leaderboard functions

---

## 📞 Need Help?

If features still aren't visible:
1. Check terminal for errors when starting server
2. Open browser console (F12) and check for JavaScript errors
3. Verify all files are saved and server restarted
4. Try accessing API directly: http://localhost:8001/api/leaderboard

---

**Made with 💗 by Team Bankrupts**
