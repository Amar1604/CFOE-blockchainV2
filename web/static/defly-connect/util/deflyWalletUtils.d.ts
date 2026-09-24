declare function generateDeflyWalletAppDeepLink(shouldAddBrowserName?: boolean): string;
declare function generateEmbeddedWalletURL(url: string): string;
/**
 * @param {string} uri WalletConnect uri
 * @returns {string} Defly Wallet deeplink
 */
declare function generateDeflyWalletConnectDeepLink(uri: string): string;
export { generateDeflyWalletAppDeepLink, generateDeflyWalletConnectDeepLink, generateEmbeddedWalletURL };
