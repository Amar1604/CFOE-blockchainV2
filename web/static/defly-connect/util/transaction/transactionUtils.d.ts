import { Transaction } from "algosdk";
import { DeflyWalletTransaction, SignerTransaction } from "../model/deflyWalletModels";
declare function encodeUnsignedTransactionInBase64(txn: Transaction): string;
declare function base64ToUint8Array(data: string): Uint8Array;
declare function composeTransaction(transaction: SignerTransaction, signerAddress?: string): DeflyWalletTransaction;
declare function formatJsonRpcRequest<T>(method: string, params: T): {
    id: number;
    jsonrpc: string;
    method: string;
    params: T;
};
export { encodeUnsignedTransactionInBase64, base64ToUint8Array, composeTransaction, formatJsonRpcRequest };
