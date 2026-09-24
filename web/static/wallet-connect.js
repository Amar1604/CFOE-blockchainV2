/**
 * Defly Wallet Integration for CfoE
 * 
 * Supports Defly Wallet (Chrome extension + mobile)
 * Handles browser Tracking Prevention blocking CDN scripts
 */

class AlgorandWalletManager {
    constructor() {
        this.wallet = null;
        this.accountAddress = null;
        this.isConnected = false;
        this.sdkLoaded = false;
        this.sdkLoadFailed = false;

        // Use local Defly Connect library (no CDN needed)
        this.localScriptPath = '/static/defly-connect/index.js';
        this.cdnSources = []; // Not using CDN anymore
    }

    async initialize() {
        try {
            const savedAddress = localStorage.getItem('cfoe_wallet_address');
            
            if (savedAddress) {
                this.accountAddress = savedAddress;
                this.isConnected = true;
                await this.notifyBackend(savedAddress);
                return true;
            }
            return false;
        } catch (error) {
            console.error('Wallet initialization failed:', error);
            return false;
        }
    }

    async connect() {
        // Skip SDK loading and go directly to manual connection
        // This avoids module resolution issues with browser-based loading
        console.log('Using manual wallet connection (no SDK required)');
        return await this.connectManual();
    }

    /**
     * Manual wallet address input fallback.
     * Used when the Defly SDK cannot be loaded due to browser Tracking Prevention
     * or other CDN blocking issues.
     */
    async connectManual() {
        return new Promise((resolve) => {
            // Create modal dialog for manual address input
            const overlay = document.createElement('div');
            overlay.id = 'wallet-manual-overlay';
            overlay.style.cssText = `
                position: fixed; inset: 0; z-index: 10000;
                background: rgba(0,0,0,0.7); backdrop-filter: blur(6px);
                display: flex; align-items: center; justify-content: center;
            `;

            const dialog = document.createElement('div');
            dialog.style.cssText = `
                background: var(--surface, #1a1a2e); color: var(--text, #e0e0e0);
                border-radius: 16px; padding: 2rem; max-width: 480px; width: 90%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.5);
                border: 1px solid rgba(255,255,255,0.1);
                font-family: 'Space Grotesk', sans-serif;
            `;

            dialog.innerHTML = `
                <h3 style="margin:0 0 0.5rem; font-size:1.25rem;">🔗 Connect Algorand Wallet</h3>
                <p style="margin:0 0 1rem; font-size:0.85rem; opacity:0.7; line-height:1.5;">
                    Enter your Algorand wallet address to connect.<br>
                    Get your address from Pera Wallet, Defly Wallet, or any Algorand wallet.
                </p>
                <input id="manual-wallet-input" type="text" placeholder="Algorand address (58 characters)"
                    style="width:100%; padding:0.75rem 1rem; border-radius:8px; border:1px solid rgba(255,255,255,0.2);
                    background:rgba(255,255,255,0.05); color:inherit; font-family:'IBM Plex Mono',monospace;
                    font-size:0.8rem; outline:none; box-sizing:border-box;" />
                <p id="manual-wallet-error" style="color:#ff6b6b; font-size:0.8rem; margin:0.5rem 0; min-height:1.2em;"></p>
                <div style="display:flex; gap:0.75rem; margin-top:1rem;">
                    <button id="manual-wallet-submit" style="flex:1; padding:0.75rem; border:none; border-radius:8px;
                        background:linear-gradient(135deg,#6c5ce7,#a855f7); color:#fff; font-weight:600;
                        cursor:pointer; font-size:0.9rem;">Connect</button>
                    <button id="manual-wallet-cancel" style="flex:1; padding:0.75rem; border:1px solid rgba(255,255,255,0.2);
                        border-radius:8px; background:transparent; color:inherit; cursor:pointer;
                        font-size:0.9rem;">Cancel</button>
                </div>
                <div style="margin:1rem 0 0; padding:1rem; background:rgba(255,255,255,0.05); border-radius:8px;">
                    <p style="margin:0 0 0.5rem; font-size:0.8rem; font-weight:600;">📱 How to get your address:</p>
                    <ul style="margin:0; padding-left:1.5rem; font-size:0.75rem; opacity:0.7; line-height:1.6;">
                        <li>Open Pera Wallet or Defly Wallet app</li>
                        <li>Tap on your account name</li>
                        <li>Copy your wallet address (starts with uppercase letters)</li>
                        <li>Paste it above and click Connect</li>
                    </ul>
                </div>
            `;

            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            const input = document.getElementById('manual-wallet-input');
            const errorEl = document.getElementById('manual-wallet-error');
            const submitBtn = document.getElementById('manual-wallet-submit');
            const cancelBtn = document.getElementById('manual-wallet-cancel');

            input.focus();

            const cleanup = () => {
                overlay.remove();
            };

            const validateAlgorandAddress = (addr) => {
                // Algorand addresses are 58 characters, uppercase A-Z and 2-7
                return /^[A-Z2-7]{58}$/.test(addr);
            };

            submitBtn.addEventListener('click', async () => {
                const address = input.value.trim().toUpperCase();
                errorEl.textContent = '';

                if (!address) {
                    errorEl.textContent = 'Please enter a wallet address.';
                    return;
                }

                if (!validateAlgorandAddress(address)) {
                    errorEl.textContent = 'Invalid Algorand address. Must be 58 characters (A-Z, 2-7).';
                    return;
                }

                this.accountAddress = address;
                this.isConnected = true;
                await this.saveSession();
                await this.notifyBackend(this.accountAddress);
                cleanup();
                resolve({ success: true, address: this.accountAddress, manual: true });
            });

            cancelBtn.addEventListener('click', () => {
                cleanup();
                resolve({ success: false, error: 'User cancelled manual connection' });
            });

            // Allow Enter key to submit
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') submitBtn.click();
                if (e.key === 'Escape') cancelBtn.click();
            });

            // Close on overlay click
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) cancelBtn.click();
            });
        });
    }

    /**
     * Load the Defly SDK from local static files.
     */
    async loadDeflySDKLocal() {
        try {
            await this._loadScript(this.localScriptPath);
            if (window.DeflyWalletConnect) {
                this.sdkLoaded = true;
                console.log('Defly SDK loaded from local files');
                return;
            }
            throw new Error('DeflyWalletConnect not found after loading script');
        } catch (e) {
            console.error('Failed to load Defly SDK from local files:', e.message);
            throw e;
        }
    }

    /**
     * Load the Defly SDK with multiple CDN fallbacks and retry logic.
     * Uses crossorigin="anonymous" to avoid storage-access issues from Tracking Prevention.
     */
    async loadDeflySDK() {
        for (let attempt = 0; attempt < 2; attempt++) {
            for (const src of this.cdnSources) {
                try {
                    await this._loadScript(src);
                    if (window.DeflyWalletConnect) {
                        this.sdkLoaded = true;
                        console.log(`Defly SDK loaded from: ${src}`);
                        return;
                    }
                } catch (e) {
                    console.warn(`Failed to load Defly SDK from ${src} (attempt ${attempt + 1}):`, e.message);
                }
            }
        }
        throw new Error('Failed to load Defly SDK from all CDN sources. Browser may be blocking third-party scripts.');
    }

    _loadScript(src) {
        return new Promise((resolve, reject) => {
            // Remove any previously failed script tags for this src
            const existing = document.querySelector(`script[src="${src}"]`);
            if (existing) existing.remove();

            const script = document.createElement('script');
            script.src = src;
            script.type = 'module'; // Use ES module for local files
            
            const timeout = setTimeout(() => {
                script.remove();
                reject(new Error(`Timeout loading script: ${src}`));
            }, 10000);

            script.onload = () => {
                clearTimeout(timeout);
                resolve();
            };
            script.onerror = () => {
                clearTimeout(timeout);
                script.remove();
                reject(new Error(`Failed to load script: ${src}`));
            };
            document.head.appendChild(script);
        });
    }

    async disconnect() {
        if (this.wallet) {
            try {
                await this.wallet.disconnect();
            } catch (error) {
                console.error('Wallet disconnect error:', error);
            }
        }
        
        this.accountAddress = null;
        this.isConnected = false;
        this.wallet = null;
        this.clearSession();
        await this.notifyBackendDisconnect();
        return { success: true };
    }

    async saveSession() {
        try {
            localStorage.setItem('cfoe_wallet_address', this.accountAddress);
        } catch (e) {
            // localStorage may also be blocked by tracking prevention
            console.warn('Could not save wallet session to localStorage:', e.message);
        }
    }

    clearSession() {
        try {
            localStorage.removeItem('cfoe_wallet_address');
        } catch (e) {
            console.warn('Could not clear wallet session from localStorage:', e.message);
        }
    }

    async notifyBackend(address) {
        try {
            const response = await fetch('/api/wallet/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address })
            });
            return await response.json();
        } catch (error) {
            console.error('Backend notification failed:', error);
        }
    }

    async notifyBackendDisconnect() {
        try {
            const response = await fetch('/api/wallet/disconnect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            return await response.json();
        } catch (error) {
            console.error('Backend disconnect notification failed:', error);
        }
    }

    getAddress() {
        return this.accountAddress;
    }

    getShortAddress() {
        if (!this.accountAddress) return null;
        return `${this.accountAddress.slice(0, 6)}...${this.accountAddress.slice(-4)}`;
    }
}

window.walletManager = new AlgorandWalletManager();
console.log('Wallet manager initialized:', window.walletManager);
