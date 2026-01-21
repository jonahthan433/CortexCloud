import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import PageTransition from '@/components/PageTransition';
import FadeIn from '@/components/FadeIn';

const Cookies = () => {
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
                    Cookie <span className="text-gradient">Policy</span>
                  </h1>
                  <p className="text-muted-foreground mb-4">Last updated: January 21, 2026</p>
                  
                  <div className="prose prose-invert max-w-none space-y-8">
                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">1. What Are Cookies</h2>
                      <p className="text-muted-foreground">
                        Cookies are small text files that are placed on your device when you visit a website. They are widely used to make websites work efficiently and provide information to website owners.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">2. How We Use Cookies</h2>
                      <p className="text-muted-foreground mb-4">CortexCloud uses cookies for the following purposes:</p>
                      <ul className="list-disc list-inside text-muted-foreground space-y-2">
                        <li><strong className="text-foreground">Essential Cookies:</strong> Required for the website to function properly, including authentication and security</li>
                        <li><strong className="text-foreground">Preference Cookies:</strong> Remember your settings and preferences</li>
                        <li><strong className="text-foreground">Analytics Cookies:</strong> Help us understand how visitors interact with our website</li>
                        <li><strong className="text-foreground">Performance Cookies:</strong> Monitor and improve website performance</li>
                      </ul>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">3. Types of Cookies We Use</h2>
                      
                      <div className="space-y-4">
                        <div>
                          <h3 className="font-semibold text-foreground mb-2">Session Cookies</h3>
                          <p className="text-muted-foreground">
                            Temporary cookies that are deleted when you close your browser. Used to maintain your session as you navigate our site.
                          </p>
                        </div>
                        
                        <div>
                          <h3 className="font-semibold text-foreground mb-2">Persistent Cookies</h3>
                          <p className="text-muted-foreground">
                            Remain on your device for a set period. Used to remember your preferences and provide a personalized experience.
                          </p>
                        </div>
                        
                        <div>
                          <h3 className="font-semibold text-foreground mb-2">First-Party Cookies</h3>
                          <p className="text-muted-foreground">
                            Set directly by CortexCloud to provide core functionality.
                          </p>
                        </div>
                        
                        <div>
                          <h3 className="font-semibold text-foreground mb-2">Third-Party Cookies</h3>
                          <p className="text-muted-foreground">
                            Set by our trusted partners for analytics and performance monitoring.
                          </p>
                        </div>
                      </div>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">4. Managing Cookies</h2>
                      <p className="text-muted-foreground mb-4">
                        You can control and manage cookies in several ways:
                      </p>
                      <ul className="list-disc list-inside text-muted-foreground space-y-2">
                        <li><strong className="text-foreground">Browser Settings:</strong> Most browsers allow you to refuse or delete cookies through settings</li>
                        <li><strong className="text-foreground">Cookie Preferences:</strong> Use our cookie consent tool to manage your preferences</li>
                        <li><strong className="text-foreground">Opt-Out Links:</strong> Many analytics providers offer opt-out mechanisms</li>
                      </ul>
                      <p className="text-muted-foreground mt-4">
                        Note: Disabling certain cookies may affect the functionality of our website.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">5. Cookie Retention</h2>
                      <p className="text-muted-foreground">
                        The length of time a cookie remains on your device depends on its type. Session cookies are deleted when you close your browser, while persistent cookies may remain for days, months, or years depending on their purpose.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">6. Updates to This Policy</h2>
                      <p className="text-muted-foreground">
                        We may update this Cookie Policy from time to time to reflect changes in our practices or for other operational, legal, or regulatory reasons. Please revisit this page periodically to stay informed.
                      </p>
                    </section>

                    <section className="glass-strong rounded-2xl p-6 md:p-8">
                      <h2 className="text-xl font-bold font-display mb-4">7. Contact Us</h2>
                      <p className="text-muted-foreground">
                        If you have questions about our use of cookies, please contact us at{' '}
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

export default Cookies;