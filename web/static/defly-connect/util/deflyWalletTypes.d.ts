type DeflyWalletType = "defly-wallet";
type DeflyWalletPlatformType = "mobile" | null;
type AlgorandChainIDs = 416001 | 416002 | 416003 | 4160;
interface DeflyWalletDetails {
    type: DeflyWalletType;
    accounts: string[];
    selectedAccount: string;
}
export type { DeflyWalletType, DeflyWalletPlatformType, DeflyWalletDetails, AlgorandChainIDs };
