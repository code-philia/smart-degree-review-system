import apiClient from './index';
export type CompletionNotification = {email:string|null;fixed:boolean;delivery_available:boolean};
export async function fetchCompletionNotification():Promise<CompletionNotification>{
  return (await apiClient.get<CompletionNotification>('/auth/notification-settings')).data;
}
export async function saveCompletionEmail(email:string):Promise<CompletionNotification>{
  return (await apiClient.put<CompletionNotification>('/auth/notification-settings',{email})).data;
}
