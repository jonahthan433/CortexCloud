import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import PageTransition from '@/components/PageTransition';
import FadeIn from '@/components/FadeIn';

const Privacy = () => {
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
                    Privacy <span className="text-gradient">Policy</span>
                  </h1>
                  <p className="text-muted-foreground mb-4">Last updated: January 21, 2026</p>
                  
                  <div className="prose prose-invert max-w-none space-y-8">
                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">1. Introduction</h2>
                      <p className="text-muted-foreground">
                        CortexCloud ("we," "our," or "us") respects your privacy and is committed to protecting your personal data. This privacy policy explains how we collect, use, disclose, and safeguard your information when you use our AI-powered automation services.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">2. Information We Collect</h2>
                      <p className="text-muted-foreground mb-4">We may collect the following types of information:</p>
                      <ul className="list-disc list-inside text-muted-foreground space-y-2">
                        <li><strong className="text-foreground">Account Information:</strong> Name, email address, and password when you create an account</li>
                        <li><strong className="text-foreground">Usage Data:</strong> Information about how you interact with our services</li>
                        <li><strong className="text-foreground">Device Information:</strong> Browser type, IP address, and device identifiers</li>
                        <li><strong className="text-foreground">Communication Data:</strong> Messages you send through our contact forms</li>
                      </ul>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">3. How We Use Your Information</h2>
                      <p className="text-muted-foreground mb-4">We use the collected information to:</p>
                      <ul className="list-disc list-inside text-muted-foreground space-y-2">
                        <li>Provide, operate, and maintain our services</li>
                        <li>Improve and personalize your experience</li>
                        <li>Communicate with you about updates and support</li>
                        <li>Ensure the security of our platform</li>
                        <li>Comply with legal obligations</li>
                      </ul>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">4. Data Sharing and Disclosure</h2>
                      <p className="text-muted-foreground">
                        We do not sell your personal information. We may share data with trusted service providers who assist in operating our services, subject to confidentiality agreements. We may also disclose information when required by law or to protect our rights.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">5. Data Security</h2>
                      <p className="text-muted-foreground">
                        We implement industry-standard security measures to protect your data, including encryption, secure servers, and regular security audits. However, no method of transmission over the internet is 100% secure.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">6. Your Rights</h2>
                      <p className="text-muted-foreground mb-4">Depending on your location, you may have the right to:</p>
                      <ul className="list-disc list-inside text-muted-foreground space-y-2">
                        <li>Access your personal data</li>
                        <li>Correct inaccurate data</li>
                        <li>Delete your data</li>
                        <li>Object to or restrict processing</li>
                        <li>Data portability</li>
                        <li>Withdraw consent</li>
                      </ul>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">7. Contact Us</h2>
                      <p className="text-muted-foreground">
                        If you have questions about this Privacy Policy or wish to exercise your rights, please contact us at{' '}
                        <a href="mailto:privacy@cortexcloud.ai" className="text-primary hover:underline">
                          privacy@cortexcloud.ai
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

export default Privacy;