import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import PageTransition from '@/components/PageTransition';
import FadeIn from '@/components/FadeIn';

const Terms = () => {
  return (
    <PageTransition>
      <div className="min-h-screen bg-background">
        <Navbar />
        
        <main className="pt-20 md:pt-32">
          <section className="py-12 md:py-24 relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-hero" />
            
            <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
              <FadeIn>
                <div className="max-w-4xl mx-auto">
                  <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary mb-6">
                    Legal
                  </span>
                  <h1 className="text-mobile-hero font-bold font-display mb-8">
                    Terms of <span className="text-gradient">Service</span>
                  </h1>
                  <p className="text-muted-foreground mb-4">Last updated: January 21, 2026</p>
                  
                  <div className="prose prose-invert max-w-none space-y-8">
                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">1. Agreement to Terms</h2>
                      <p className="text-muted-foreground">
                        By accessing or using CortexCloud's services, you agree to be bound by these Terms of Service. If you disagree with any part of these terms, you may not access our services.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">2. Description of Services</h2>
                      <p className="text-muted-foreground">
                        CortexCloud provides AI-powered automation solutions, including intelligent agents, workflow automation, and customer service tools. Our services are designed to help businesses streamline operations and improve productivity.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">3. User Accounts</h2>
                      <p className="text-muted-foreground mb-4">When creating an account, you agree to:</p>
                      <ul className="list-disc list-inside text-muted-foreground space-y-2">
                        <li>Provide accurate and complete information</li>
                        <li>Maintain the security of your account credentials</li>
                        <li>Notify us immediately of any unauthorized access</li>
                        <li>Accept responsibility for all activities under your account</li>
                      </ul>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">4. Acceptable Use</h2>
                      <p className="text-muted-foreground mb-4">You agree not to:</p>
                      <ul className="list-disc list-inside text-muted-foreground space-y-2">
                        <li>Use our services for any illegal purpose</li>
                        <li>Attempt to gain unauthorized access to our systems</li>
                        <li>Interfere with or disrupt our services</li>
                        <li>Upload malicious code or content</li>
                        <li>Violate any applicable laws or regulations</li>
                      </ul>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">5. Intellectual Property</h2>
                      <p className="text-muted-foreground">
                        All content, features, and functionality of our services are owned by CortexCloud and are protected by copyright, trademark, and other intellectual property laws. You may not reproduce, distribute, or create derivative works without our prior written consent.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">6. Payment Terms</h2>
                      <p className="text-muted-foreground">
                        Paid services are billed in advance on a subscription basis. You agree to pay all applicable fees as described in your selected plan. Refunds are provided in accordance with our refund policy.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">7. Limitation of Liability</h2>
                      <p className="text-muted-foreground">
                        To the maximum extent permitted by law, CortexCloud shall not be liable for any indirect, incidental, special, consequential, or punitive damages arising from your use of our services.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">8. Termination</h2>
                      <p className="text-muted-foreground">
                        We reserve the right to suspend or terminate your account at any time for violations of these terms. Upon termination, your right to use our services will immediately cease.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">9. Changes to Terms</h2>
                      <p className="text-muted-foreground">
                        We may update these terms from time to time. We will notify you of any material changes by posting the new terms on this page and updating the "Last updated" date.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">10. Contact Us</h2>
                      <p className="text-muted-foreground">
                        If you have questions about these Terms of Service, please contact us at{' '}
                        <a href="mailto:legal@cortexcloud.ai" className="text-primary hover:underline">
                          legal@cortexcloud.ai
                        </a>
                      </p>
                    </section>
                  </div>
                </div>
              </FadeIn>
            </div>
          </section>
        </main>

        <Footer />
      </div>
    </PageTransition>
  );
};

export default Terms;