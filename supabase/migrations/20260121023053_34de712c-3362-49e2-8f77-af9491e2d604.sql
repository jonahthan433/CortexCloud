-- Add DELETE policy for profiles table (GDPR compliance)
CREATE POLICY "Users can delete own profile"
ON public.profiles
FOR DELETE
USING (auth.uid() = user_id);