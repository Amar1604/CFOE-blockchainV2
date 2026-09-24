import { IWalletConnectSession } from "@walletconnect/types";
import { DeflyWalletDetails, DeflyWalletPlatformType } from "../deflyWalletTypes";
declare function getLocalStorage(): Storage | undefined;
declare function saveWalletDetailsToStorage(accounts: string[], type?: "defly-wallet"): void;
declare function getWalletDetailsFromStorage(): DeflyWalletDetails | null;
declare function getWalletConnectObjectFromStorage(): IWalletConnectSession | null;
declare function resetWalletDetailsFromStorage(): Promise<undefined>;
declare function getWalletPlatformFromStorage(): DeflyWalletPlatformType;
export { getLocalStorage, saveWalletDetailsToStorage, resetWalletDetailsFromStorage, getWalletDetailsFromStorage, getWalletConnectObjectFromStorage, getWalletPlatformFromStorage };
