export interface DeflyWalletModalConfig {
    shouldUseSound: boolean;
}
declare const DEFLY_WALLET_CONNECT_MODAL_ID = "defly-wallet-connect-modal-wrapper";
declare const DEFLY_WALLET_REDIRECT_MODAL_ID = "defly-wallet-redirect-modal-wrapper";
declare const DEFLY_WALLET_SIGN_TXN_TOAST_ID = "defly-wallet-sign-txn-toast-wrapper";
declare const DEFLY_WALLET_SIGN_TXN_MODAL_ID = "defly-wallet-sign-txn-modal-wrapper";
declare const DEFLY_WALLET_MODAL_CLASSNAME = "defly-wallet-modal";
declare function openDeflyWalletConnectModal(modalConfig: DeflyWalletModalConfig): (uri: string) => void;
declare function setupDeflyWalletConnectModalCloseListener(onClose: VoidFunction): void;
/**
 * Creates a DeflyWalletRedirectModal instance and renders it on the DOM.
 *
 * @returns {void}
 */
declare function openDeflyWalletRedirectModal(): void;
declare function openDeflyWalletSignTxnModal(): Promise<Element>;
declare function closeDeflyWalletSignTxnModal(rejectPromise?: (error: any) => void): void;
/**
 * Creates a DeflyWalletSignTxnToast instance and renders it on the DOM.
 *
 * @returns {void}
 */
declare function openDeflyWalletSignTxnToast(): void;
declare function closeDeflyWalletSignTxnToast(): void;
declare function removeModalWrapperFromDOM(modalId: string): void;
export { DEFLY_WALLET_CONNECT_MODAL_ID, DEFLY_WALLET_REDIRECT_MODAL_ID, DEFLY_WALLET_SIGN_TXN_TOAST_ID, DEFLY_WALLET_SIGN_TXN_MODAL_ID, DEFLY_WALLET_MODAL_CLASSNAME, openDeflyWalletConnectModal, setupDeflyWalletConnectModalCloseListener, openDeflyWalletRedirectModal, openDeflyWalletSignTxnToast, closeDeflyWalletSignTxnToast, removeModalWrapperFromDOM, openDeflyWalletSignTxnModal, closeDeflyWalletSignTxnModal };
