import { DeflyWalletConfig } from './deflyWalletConnectApiTypes';
/**
 * @returns {object} {use_sound: boolean, servers: string[]}
 */
declare function fetchDeflyConnectConfig(): Promise<{
    use_sound: boolean | undefined;
    servers: string[] | undefined;
    silent: boolean | undefined;
}>;
/**
 * @returns {object} {bridgeURL: string, shouldUseSound: boolean}
 */
declare function getDeflyConnectConfig(): Promise<DeflyWalletConfig>;
export { getDeflyConnectConfig, fetchDeflyConnectConfig };
