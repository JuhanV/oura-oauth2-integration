-- Add delete policy for oura_tokens table
create policy "Users can delete tokens"
    on oura_tokens for delete
    using (true);

-- Create function to delete tokens
create or replace function delete_token(target_profile_id uuid)
returns void as $$
begin
    delete from oura_tokens where profile_id = target_profile_id;
end;
$$ language plpgsql security definer; 