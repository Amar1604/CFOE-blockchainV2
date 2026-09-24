import WalletConnect from '@walletconnect/client';
import { SignerTransaction } from './util/model/deflyWalletModels';
import { AlgorandChainIDs } from './util/deflyWalletTypes';
interface DeflyWalletConnectOptions {
    bridge?: string;
    shouldShowSignTxnToast?: boolean;
    chainId?: AlgorandChainIDs;
}
declare class DeflyWalletConnect {
    bridge: string;
    connector: WalletConnect | null;
    shouldShowSignTxnToast: boolean;
    chainId?: number;
    constructor(options?: DeflyWalletConnectOptions);
    get platform(): import("./util/deflyWalletTypes").DeflyWalletPlatformType;
    get isConnected(): boolean;
    connect(): Promise<string[]>;
    reconnectSession(): Promise<string[]>;
    disconnect(): Promise<void>;
    private signTransactionWithMobile;
    signTransaction(txGroups: SignerTransaction[][], signerAddress?: string): Promise<Uint8Array[]>;
}
export default DeflyWalletConnect;
